use crate::{
    http::Http,
    metrics::Metrics,
    model::{
        self, Config, Error, Result, Supply, date, format, human, long_sleep, short_sleep, text,
    },
};
use async_trait::async_trait;
use futures_util::StreamExt;
use md5::{Digest, Md5};
use mongodb::{
    Database,
    bson::{Document, doc},
    options::ReturnDocument,
};
use reqwest::Method;
use serde_json::{Value, json};
use std::{collections::HashMap, sync::Arc, time::Duration};
use tokio::{process::Command, sync::Semaphore};

pub const MEDIA_LIMIT: u64 = 50 * 1024 * 1024;
#[derive(Clone)]
pub struct Media {
    pub kind: String,
    pub url: String,
    pub groups: Vec<Vec<Value>>,
}
impl Media {
    fn link(kind: &str, url: &str) -> Self {
        Self {
            kind: kind.into(),
            url: url.into(),
            groups: vec![],
        }
    }
}

#[async_trait]
pub trait AckSink: Send + Sync {
    async fn record(&self, ids: Vec<i64>) -> Result<()>;
}

#[derive(Clone)]
pub struct Sender {
    pub config: Arc<Config>,
    pub db: Database,
    pub destination: Value,
    pub http: Http,
    pub media: Http,
    pub videos: Arc<Semaphore>,
    pub metrics: Metrics,
    pub acknowledgement: Option<Arc<dyn AckSink>>,
}
impl Sender {
    pub async fn new(
        config: Arc<Config>,
        db: Database,
        destination: Value,
        metrics: Metrics,
        videos: Arc<Semaphore>,
    ) -> Result<Self> {
        let sender = Self {
            config,
            db,
            destination,
            http: Http::new(metrics.clone(), 30)?,
            media: Http::new(metrics.clone(), 5)?,
            videos,
            metrics,
            acknowledgement: None,
        };
        short_sleep(1.).await;
        Ok(sender)
    }
    pub fn channel(&self) -> String {
        self.destination
            .as_str()
            .map(str::to_owned)
            .unwrap_or_else(|| self.destination.to_string())
    }
    pub async fn api(&self, method: &str, mut params: Value) -> Result<Value> {
        if params.get("chat_id").is_none()
            && (method.starts_with("send")
                || method == "getChatMemberCount"
                || method == "getChatAdministrators")
        {
            params["chat_id"] = self.destination.clone();
        }
        let result = self
            .http
            .telegram(
                text(&self.config.values["telegram"], "token"),
                method,
                params,
            )
            .await?;
        if method.starts_with("send") || method == "forwardMessage" {
            self.ack(&result).await?;
        }
        Ok(result)
    }
    async fn ack(&self, result: &Value) -> Result<()> {
        if let Some(sink) = &self.acknowledgement {
            let ids = if let Some(items) = result.as_array() {
                items
                    .iter()
                    .filter_map(|v| v["message_id"].as_i64())
                    .collect()
            } else {
                result["message_id"].as_i64().into_iter().collect()
            };
            sink.record(ids).await?;
        }
        Ok(())
    }
    pub async fn send_text(
        &self,
        body: &str,
        preview: bool,
        parse: Option<&str>,
    ) -> Result<Supply> {
        let mut remaining = body.to_owned();
        let split = remaining.chars().count() >= 4096;
        loop {
            let (part, next) = if !split {
                (remaining, String::new())
            } else {
                split_message(&remaining)
            };
            let mut params = json!({"text":part,"disable_web_page_preview":preview});
            if let Some(parse) = parse {
                params["parse_mode"] = json!(parse);
            }
            self.api("sendMessage", params).await?;
            if split {
                short_sleep(1.).await;
            }
            if next.is_empty() {
                break;
            }
            remaining = next;
        }
        Ok(Supply::Sent)
    }
    pub async fn send_img(&self, url: &str, body: &str) -> Result<Supply> {
        if body.chars().count() > 1024 {
            return self
                .send_text(
                    &format!("<a href=\"{url}\">&#160;</a>{body}"),
                    false,
                    Some("HTML"),
                )
                .await;
        }
        match self
            .api("sendPhoto", json!({"photo":url,"caption":body}))
            .await
        {
            Ok(_) => Ok(Supply::Sent),
            Err(
                Error::Rejected
                | Error::Telegram
                | Error::Network
                | Error::Timeout
                | Error::Forbidden
                | Error::RateLimit,
            ) => Ok(Supply::Skip),
            Err(error) => Err(error),
        }
    }
    pub async fn send_gif(&self, url: &str, body: &str) -> Result<Supply> {
        if self.url_size(url).await? > MEDIA_LIMIT {
            return Ok(Supply::Reject);
        }
        let (caption, tail) = split_caption(body);
        match self
            .api("sendDocument", json!({"document":url,"caption":caption}))
            .await
        {
            Ok(_) => {}
            Err(Error::Rejected) => return Ok(Supply::Skip),
            Err(e) => return Err(e),
        }
        if tail.chars().count() > 1 {
            short_sleep(1.).await;
            self.send_text(&tail, true, None).await?;
        }
        Ok(Supply::Sent)
    }
    pub async fn send_gallery(&self, groups: &[Vec<Value>], body: &str) -> Result<Supply> {
        self.send_text(body, false, None).await?;
        long_sleep(1.).await;
        for (index, items) in groups.iter().enumerate() {
            // The Python implementation logs an album API failure and proceeds.
            let _ = self.api("sendMediaGroup", json!({"media":items})).await;
            long_sleep((index + 2) as f64).await;
        }
        Ok(Supply::Sent)
    }
    pub async fn send_video(&self, url: &str, body: &str, dash: Option<&str>) -> Result<Supply> {
        let _slot = self.videos.acquire().await.map_err(|_| Error::Media)?;
        let folder = self.config.app.join("tmp");
        tokio::fs::create_dir_all(&folder).await?;
        let files = tempfile::Builder::new().prefix("r2t-").tempdir_in(folder)?;
        let video = files.path().join("media.mp4");
        if !self.media.download(url, &video, MEDIA_LIMIT).await? {
            return Ok(Supply::Reject);
        }
        let mut send = video.clone();
        let audio_url = if let Some(dash) = dash {
            self.dash_audio(dash).await
        } else {
            None
        }
        .unwrap_or_else(|| {
            format!(
                "{}/DASH_AUDIO_128.mp4",
                url.rsplit_once('/').map(|(base, _)| base).unwrap_or(url)
            )
        });
        let audio = files.path().join("media.mp4.aac");
        if self.media.download(&audio_url, &audio, MEDIA_LIMIT).await? {
            let muxed = files.path().join("media.1.mp4");
            let mut command = Command::new("ffmpeg");
            command
                .args([
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-threads",
                    "1",
                    "-i",
                ])
                .arg(&video)
                .args(["-threads", "1", "-i"])
                .arg(&audio)
                .args(["-map", "0:v:0", "-map", "1:a:0", "-c", "copy"])
                .arg(&muxed)
                .stdout(std::process::Stdio::null())
                .stderr(std::process::Stdio::null())
                .kill_on_drop(true);
            if let Ok(Ok(status)) =
                tokio::time::timeout(Duration::from_secs(60), command.status()).await
            {
                if status.success() && tokio::fs::metadata(&muxed).await.is_ok_and(|m| m.len() > 0)
                {
                    send = muxed;
                }
            }
        }
        let size = tokio::fs::metadata(&send).await?.len();
        if size == 0 || size > MEDIA_LIMIT {
            return Ok(Supply::Reject);
        }
        let (caption, tail) = split_caption(body);
        let result = self
            .http
            .telegram_video(
                text(&self.config.values["telegram"], "token"),
                &json!({"chat_id":self.destination,"caption":caption}),
                &send,
            )
            .await?;
        self.ack(&result).await?;
        if tail.chars().count() > 1 {
            short_sleep(1.).await;
            self.send_text(&tail, true, None).await?;
        }
        Ok(Supply::Sent)
    }
    async fn dash_audio(&self, url: &str) -> Option<String> {
        let body = self.media.metadata(url).await.ok()?;
        let pattern = regex::Regex::new(r"<BaseURL>([^<]+)</BaseURL>").ok()?;
        let audio = pattern
            .captures_iter(&body)
            .filter_map(|c| c.get(1).map(|m| m.as_str().to_owned()))
            .filter(|u| u.to_uppercase().contains("AUDIO"))
            .last()?;
        let base = url.split("DASHPlaylist.mpd").next()?;
        let query = url
            .split_once('?')
            .map(|(_, q)| format!("?{q}"))
            .unwrap_or_default();
        Some(format!("{base}{audio}{query}"))
    }
    async fn url_size(&self, url: &str) -> Result<u64> {
        match self.media.request(Method::HEAD, url, 8).await {
            Ok(response) => match response.headers().get("content-length") {
                Some(n) => n
                    .to_str()
                    .ok()
                    .and_then(|s| s.parse().ok())
                    .ok_or(Error::Media),
                None => Ok(0),
            },
            Err(_) => Ok(0),
        }
    }
    pub async fn was_before(&self, url: &str) -> Result<bool> {
        let urls = self.db.collection::<Document>("urls");
        let channel = self.channel().to_lowercase();
        let id = url.rsplit('/').next().unwrap_or(url);
        for filter in [
            doc! {"channel":&channel,"url_id":id},
            doc! {"channel":&channel,"url":url.to_lowercase()},
            doc! {"channel":&channel,"url":{"$regex":regex::escape(id)}},
        ] {
            if urls
                .find_one(filter)
                .projection(doc! {"_id":1})
                .await?
                .is_some()
            {
                self.metrics.count("previously_seen_candidates", 1);
                return Ok(true);
            }
        }
        Ok(false)
    }
    pub async fn too_many_errors(&self, url: &str) -> Result<bool> {
        Ok(self
            .db
            .collection::<Document>("errors")
            .find_one(doc! {"channel":self.channel().to_lowercase(),"url":url.to_lowercase()})
            .await?
            .and_then(|d| model::numeric(&d, "cnt"))
            .is_some_and(|n| n >= 2.))
    }
    pub async fn mark(&self, url: &str, sent: bool) -> Result<()> {
        self.db.collection::<Document>("urls").insert_one(doc!{"url_id":url.rsplit('/').next().unwrap_or(url),"url":url.to_lowercase(),"ts":date(),"channel":self.channel().to_lowercase(),"sent":sent}).await?;
        self.metrics.post(&self.channel(), url, sent);
        Ok(())
    }
    async fn duplicate(&self, url: &str) -> Result<bool> {
        let response = match self.media.request(Method::GET, url, 20).await {
            Ok(r) => r,
            Err(_) => return Ok(false),
        };
        if !response.status().is_success()
            || response.content_length().is_some_and(|n| n > MEDIA_LIMIT)
        {
            return Ok(false);
        }
        let mut stream = response.bytes_stream();
        let mut hash = Md5::new();
        let mut size = 0;
        while let Some(chunk) = tokio::time::timeout(Duration::from_secs(20), stream.next())
            .await
            .map_err(|_| Error::Timeout)?
        {
            let chunk = chunk.map_err(|_| Error::Network)?;
            size += chunk.len() as u64;
            self.metrics
                .count("http_response_body_bytes", chunk.len() as u64);
            if size > MEDIA_LIMIT {
                return Ok(false);
            }
            hash.update(chunk);
        }
        let digest = format!("{:x}", hash.finalize());
        let before=self.db.collection::<Document>("contents").find_one_and_update(doc!{"channel":self.channel().to_lowercase(),"md5_sum":&digest},
            doc!{"$setOnInsert":{"channel":self.channel().to_lowercase(),"md5_sum":digest,"ts":date()}}).upsert(true).return_document(ReturnDocument::Before).await?;
        if before.is_some() {
            self.metrics.count("duplicate_media_candidates", 1);
        }
        Ok(before.is_some())
    }
    pub async fn classify(&self, submission: &Value) -> Result<Media> {
        let url = text(submission, "url");
        let parsed = url::Url::parse(url)?;
        let host = parsed.host_str().unwrap_or("");
        let lower = url.to_lowercase();
        if let Some(items) = submission["gallery_data"]["items"].as_array() {
            let mut media = Vec::new();
            let numeric = items.iter().all(|item| item["id"].as_i64().is_some());
            let strings = items.iter().all(|item| item["id"].as_str().is_some());
            if !numeric && !strings {
                return Err(Error::Media);
            }
            let mut ordered: Vec<_> = items.iter().rev().collect();
            ordered.sort_by(|a, b| {
                if numeric {
                    a["id"].as_i64().cmp(&b["id"].as_i64())
                } else {
                    a["id"].as_str().cmp(&b["id"].as_str())
                }
            });
            ordered.dedup_by(|a, b| a["id"] == b["id"]);
            for item in ordered {
                let source = &submission["media_metadata"][text(item, "media_id")]["s"];
                let (kind, link) = if let Some(s) = source["u"].as_str() {
                    ("photo", s)
                } else {
                    ("video", source["mp4"].as_str().ok_or(Error::Media)?)
                };
                let decoded = html_escape::decode_html_entities(link);
                let normalized = if let Ok(parsed) = url::Url::parse(&decoded) {
                    if parsed.host_str() == Some("preview.redd.it") {
                        format!("https://i.redd.it{}", parsed.path())
                    } else {
                        decoded.replace("auto=webp", "auto=jpg")
                    }
                } else {
                    decoded.replace("auto=webp", "auto=jpg")
                };
                media.push(json!({"type":kind,"media":normalized}));
            }
            return Ok(Media {
                kind: "gallery".into(),
                url: String::new(),
                groups: media.chunks(10).map(<[Value]>::to_vec).collect(),
            });
        }
        let mut video = &submission["media"]["reddit_video"];
        if !submission["is_video"].as_bool().unwrap_or(false) {
            video = &Value::Null;
        }
        if video.is_null() {
            if let Some(cross) = submission["crosspost_parent_list"]
                .as_array()
                .and_then(|a| a.first())
            {
                if cross["is_video"] == true {
                    video = &cross["media"]["reddit_video"];
                }
            }
        }
        if !video.is_null() {
            return Ok(Media::link(
                if video["is_gif"] == true {
                    "gif"
                } else {
                    "video"
                },
                text(video, "fallback_url"),
            ));
        }
        if submission["is_self"] == true {
            return Ok(Media::link("text", ""));
        }
        if host == "i.redd.it" && [".jpg", ".jpeg", ".png"].iter().any(|s| lower.ends_with(s)) {
            return Ok(Media::link("img", url));
        }
        if matches!(host, "i.imgur.com" | "i.stack.imgur.com") {
            if lower.ends_with(".gifv") {
                return Ok(Media::link(
                    "gif",
                    &format!("{}.mp4", &url[..url.len() - 5]),
                ));
            }
            if lower.ends_with(".gif") || lower.ends_with(".mp4") {
                return Ok(Media::link("gif", url));
            }
            if [".jpg", ".jpeg", ".png"].iter().any(|s| lower.ends_with(s)) {
                return Ok(Media::link("img", url));
            }
        }
        let mime = match self.media.request(Method::HEAD, url, 8).await {
            Ok(r) => r
                .headers()
                .get("content-type")
                .and_then(|v| v.to_str().ok())
                .unwrap_or("")
                .to_owned(),
            Err(_) => String::new(),
        };
        if mime == "image/jpeg" || mime == "image/png" {
            return Ok(Media::link("img", url));
        }
        if mime.contains("image/gif") {
            if url.ends_with(".gif") {
                let mp4 = format!("{}.mp4", &url[..url.len() - 4]);
                if self
                    .media
                    .request(Method::HEAD, &mp4, 8)
                    .await
                    .is_ok_and(|r| {
                        r.headers()
                            .get("content-type")
                            .is_some_and(|v| v == "video/mp4")
                    })
                {
                    return Ok(Media::link("gif", &mp4));
                }
            }
            return Ok(Media::link("gif", url));
        }
        if url.ends_with(".gifv") {
            let mp4 = format!("{}.mp4", &url[..url.len() - 5]);
            if self
                .media
                .request(Method::HEAD, &mp4, 8)
                .await
                .is_ok_and(|r| {
                    r.headers()
                        .get("content-type")
                        .is_some_and(|v| v == "video/mp4")
                })
            {
                return Ok(Media::link("gif", &mp4));
            }
            let gif = &url[..url.len() - 1];
            if self
                .media
                .request(Method::HEAD, gif, 8)
                .await
                .is_ok_and(|r| {
                    r.headers()
                        .get("content-type")
                        .is_some_and(|v| v == "image/gif")
                })
            {
                return Ok(Media::link("gif", gif));
            }
        }
        if matches!(host, "imgur.com" | "www.imgur.com" | "m.imgur.com") {
            return self.imgur(url, &parsed).await;
        }
        if host.contains("gfycat.com") {
            let parts: Vec<_> = parsed.path().trim_start_matches('/').split('/').collect();
            let name = if parts.first() == Some(&"detail") {
                parts.get(1)
            } else {
                parts.first()
            };
            if let Some(name) = name {
                if let Ok(content) = self
                    .media
                    .metadata(&format!("https://api.gfycat.com/v1/gfycats/{name}"))
                    .await
                {
                    if let Ok(data) = serde_json::from_str::<Value>(&content) {
                        if let Some(link) = data["gfyItem"]["mp4Url"].as_str() {
                            return Ok(Media::link("gif", link));
                        }
                    }
                }
            }
        }
        Ok(Media::link("other", url))
    }
    async fn imgur(&self, url: &str, parsed: &url::Url) -> Result<Media> {
        let mut config = self.config.values["imgur"].clone();
        if config.is_null() {
            if let Ok(bytes) = std::fs::read(self.config.app.join("configs/imgur.yml")) {
                config = serde_yaml::from_slice(&bytes).unwrap_or(Value::Null);
            }
        }
        if config.is_null() {
            return Ok(Media::link("other", url));
        }
        let parts: Vec<_> = parsed.path().split('/').filter(|p| !p.is_empty()).collect();
        if parts.is_empty() || parts[0] == "topic" {
            return Ok(Media::link("other", url));
        }
        let album = parts[0] == "a" || parts[0] == "gallery";
        let identifier = if album {
            parts.get(1).copied().unwrap_or("")
        } else {
            parts.last().copied().unwrap_or("")
        };
        let id = identifier.split('.').next().unwrap_or("");
        for endpoint in if album {
            vec!["album", "image"]
        } else {
            vec!["image"]
        } {
            if endpoint == "image" && parts[0] == "a" {
                break;
            }
            let response = self
                .media
                .send(
                    self.media
                        .client
                        .get(format!("https://api.imgur.com/3/{endpoint}/{id}"))
                        .header(
                            "Authorization",
                            format!("Client-ID {}", text(&config, "client_id")),
                        ),
                    20,
                    "http",
                )
                .await;
            if let Ok(response) = response {
                if let Ok(data) = self.media.json(response, 20, "http").await {
                    if data["success"] != true {
                        continue;
                    }
                    let image = |v: &Value| -> Value {
                        let animated = v["animated"] == true;
                        let link = if animated {
                            v["mp4"]
                                .as_str()
                                .filter(|v| !v.is_empty())
                                .or_else(|| v["gifv"].as_str().filter(|v| !v.is_empty()))
                                .unwrap_or_else(|| text(v, "link"))
                        } else {
                            text(v, "link")
                        };
                        let link = if link.ends_with(".gifv") {
                            &link[..link.len() - 1]
                        } else {
                            link
                        };
                        json!({"type":if animated{"video"}else{"photo"},"media":link})
                    };
                    if let Some(images) = data["data"]["images"].as_array() {
                        let items: Vec<_> = images.iter().map(image).collect();
                        return Ok(Media {
                            kind: "album".into(),
                            url: url.into(),
                            groups: items.chunks(10).map(<[Value]>::to_vec).collect(),
                        });
                    }
                    let item = image(&data["data"]);
                    return Ok(Media::link(
                        if data["data"]["animated"] == true {
                            "gif"
                        } else {
                            "img"
                        },
                        text(&item, "media"),
                    ));
                }
            }
        }
        Ok(Media::link("other", url))
    }
    pub async fn simple(&self, submission: &Value, options: &Value) -> Result<Supply> {
        let score = model::number(submission, "score", 0);
        if options["min_upvotes_limit"]
            .as_i64()
            .is_some_and(|min| score < min)
        {
            return Ok(Supply::Skip);
        }
        let media = match self.classify(submission).await {
            Ok(media) => media,
            Err(_) => return Ok(Supply::Skip),
        };
        if options
            .get("nsfw_filter_out")
            .map(model::truth)
            .unwrap_or(true)
            && submission["over_18"] == true
        {
            return Ok(Supply::Reject);
        }
        if options["check_dups"] == true
            && !media.url.is_empty()
            && self.duplicate(&media.url).await?
        {
            return Ok(Supply::Reject);
        }
        let rule = options.get(&media.kind).unwrap_or(&Value::Bool(true));
        if !model::truth(rule) {
            return Ok(Supply::Reject);
        }
        let mut fields = HashMap::from([
            ("what".into(), media.kind.clone()),
            ("url".into(), media.url.clone()),
            ("title".into(), text(submission, "title").into()),
            ("self_text".into(), text(submission, "selftext").into()),
            ("link".into(), text(submission, "url").into()),
            (
                "short_link".into(),
                format!("https://redd.it/{}", text(submission, "id")),
            ),
            (
                "subreddit_name".into(),
                text(submission, "subreddit").into(),
            ),
            ("score".into(), score.to_string()),
            ("upvotes".into(), human(score)),
            ("channel".into(), self.channel()),
        ]);
        if let Some(options) = options.as_object() {
            for (key, value) in options {
                fields.insert(
                    key.clone(),
                    value
                        .as_str()
                        .map(str::to_owned)
                        .unwrap_or_else(|| value.to_string()),
                );
            }
        }
        let default = match media.kind.as_str() {
            "text" => "{title}\n\n{self_text}\n\n{short_link}\n{channel}",
            "video" | "gallery" => "{title}\n\n{short_link}\n{channel}",
            "album" | "other" => "{title}\n{link}\n\n{short_link}\n{channel}",
            _ => "{title}\n{short_link}\n{channel}",
        };
        let template = rule.as_str().unwrap_or(default);
        if media.kind == "text" {
            if let Some(limit) = options["max_selftext_len"].as_u64() {
                fields.insert(
                    "self_text".into(),
                    format!(
                        "{}...",
                        text(submission, "selftext")
                            .chars()
                            .take(limit as usize)
                            .collect::<String>()
                    ),
                );
            }
            let preview = options["disable_web_page_preview"]
                .as_bool()
                .unwrap_or(false);
            let markdown = format(
                &template
                    .replace("{short_link}", "[{short_link}]({short_link})")
                    .replace("{channel}", "[{channel}]({channel})"),
                &fields,
            )?;
            return match self.send_text(&markdown, preview, Some("Markdown")).await {
                Err(Error::Rejected) => {
                    self.send_text(&format(template, &fields)?, preview, None)
                        .await
                }
                other => other,
            };
        }
        let body = format(template, &fields)?;
        match media.kind.as_str() {
            "img" => self.send_img(&media.url, &body).await,
            "gif" => self.send_gif(&media.url, &body).await,
            "video" => {
                self.send_video(
                    &media.url,
                    &body,
                    submission["media"]["reddit_video"]["dash_url"].as_str(),
                )
                .await
            }
            "gallery" | "album" => self.send_gallery(&media.groups, &body).await,
            _ => self.send_text(&body, false, None).await,
        }
    }
}

fn split_message(body: &str) -> (String, String) {
    let words: Vec<_> = body.split(' ').collect();
    if words[0].chars().count() > 4096 {
        return (
            body.chars().take(4096).collect(),
            body.chars().skip(4096).collect(),
        );
    }
    let mut size = 0;
    let mut take = 0;
    for word in &words {
        let n = word.chars().count();
        if size + take + n > 4096 {
            break;
        }
        size += n;
        take += 1;
    }
    (words[..take].join(" "), words[take..].join(" "))
}
fn split_caption(body: &str) -> (String, String) {
    if body.chars().count() <= 1024 {
        return (body.into(), String::new());
    }
    let mut caption = String::new();
    let mut tail = String::new();
    let mut switched = false;
    for word in body.split([' ', '\n']) {
        if !switched && caption.chars().count() + word.chars().count() + 1 < 1020 {
            caption.push_str(word);
            caption.push(' ');
        } else {
            switched = true;
            tail.push(' ');
            tail.push_str(word);
        }
    }
    (caption + " ...", "... ".to_owned() + &tail)
}
pub async fn clean(config: &Config, channel: Option<&str>) -> Result<u64> {
    long_sleep(1. / (std::f64::consts::PI * std::f64::consts::E)).await;
    let mut deleted = 0;
    let folder = config.app.join("tmp");
    for entry in std::fs::read_dir(folder)? {
        let entry = entry?;
        let path = entry.path();
        if !path.is_file() {
            continue;
        }
        let name = entry.file_name().to_string_lossy().into_owned();
        if name == "empty.md" {
            continue;
        }
        if channel.is_some_and(|c| !name.contains(c.get(1..).unwrap_or(""))) {
            continue;
        }
        let bytes = entry.metadata()?.len();
        if std::fs::remove_file(path).is_ok() {
            deleted += bytes;
        }
    }
    Ok(deleted)
}
