use crate::{
    custom,
    model::{self, Error, Result, Supply, text},
    queue::App,
    sender::{self, Sender},
};
use chrono::Utc;
use futures_util::TryStreamExt;
use mongodb::{
    IndexModel,
    bson::{self, Bson, Document, doc},
    options::IndexOptions,
};
use rand::seq::SliceRandom;
use serde_json::{Value, json};
use std::{
    collections::{BTreeSet, HashMap},
    time::Duration,
};

pub async fn cleaner(app: &App, sender: &Sender) -> Result<Supply> {
    let info = std::fs::read_to_string("/proc/meminfo")?;
    let free = info
        .lines()
        .find_map(|line| line.strip_prefix("MemFree:"))
        .and_then(|n| n.split_whitespace().next())
        .and_then(|n| n.parse::<f64>().ok())
        .ok_or(Error::Io)?
        / 1024.;
    let deleted = sender::clean(&app.config, None).await?;
    let mut disk = std::mem::MaybeUninit::<libc::statvfs>::uninit();
    let available = unsafe {
        if libc::statvfs(c"/".as_ptr(), disk.as_mut_ptr()) != 0 {
            return Err(Error::Io);
        }
        let disk = disk.assume_init();
        disk.f_bavail as f64 * disk.f_frsize as f64 / 1024f64.powi(3)
    };
    let output = tokio::process::Command::new("vnstat")
        .arg("-m")
        .output()
        .await?;
    if !output.status.success() {
        return Err(Error::Io);
    }
    let output = String::from_utf8_lossy(&output.stdout);
    let lines: Vec<_> = output.split('\n').collect();
    let traffic = lines
        .get(lines.len().saturating_sub(4))
        .and_then(|l| l.split(" | ").rev().nth(1))
        .ok_or(Error::Io)?
        .trim();
    let estimate = lines
        .get(lines.len().saturating_sub(2))
        .and_then(|l| l.split('|').rev().nth(1))
        .ok_or(Error::Io)?
        .trim();
    let tasks = app.db.collection::<Document>("tasks");
    let mut cursor = tasks
        .aggregate(vec![doc! {"$group":{"_id":"$status","count":{"$sum":1}}}])
        .await?;
    let mut counts = HashMap::new();
    while let Some(record) = cursor.try_next().await? {
        if let (Some(id), Some(count)) = (
            model::numeric(&record, "_id"),
            model::numeric(&record, "count"),
        ) {
            counts.insert(id as i64, count as i64);
        }
    }
    let settings = app.db.collection::<Document>("settings");
    let previous = settings.find_one(doc! {"setting":"tasks-stati"}).await?;
    let mut data = previous
        .and_then(|d| d.get_document("data").ok().cloned())
        .unwrap_or_default();
    let cycles = data
        .values()
        .filter_map(Bson::as_document)
        .filter_map(|d| model::numeric(d, "cycles_cnt"))
        .fold(0f64, f64::max) as i64
        + 1;
    let mut body = format!(
        "Free memory: {free:.3}MB.\nDeleted files: {:.3}GB.\nAvailable disk space: {available:.3}GB.\nCurrent month traffic: {traffic}.\nCurrent month estimate: {estimate}.\nTasks' stati:\n",
        deleted as f64 / 1024f64.powi(3)
    );
    let mut removed = 0;
    for (status, name) in [
        (1, "NEW"),
        (2, "IN_PROGRESS"),
        (3, "SUCCESS"),
        (4, "FAILED"),
        (5, "SCHEDULED"),
    ] {
        let mut stat = data
            .get_document(name)
            .cloned()
            .unwrap_or_else(|_| doc! {"amt":0,"cycles_cnt":0});
        let count = *counts.get(&status).unwrap_or(&0);
        let total = model::numeric(&stat, "amt").unwrap_or(0.) as i64 + count;
        stat.insert("amt", total);
        stat.insert(
            "cycles_cnt",
            model::numeric(&stat, "cycles_cnt").unwrap_or(0.) as i64 + 1,
        );
        body.push_str(&format!(
            "  →  {name}: {count} (avg: {:.3})\n",
            total as f64 / cycles as f64
        ));
        data.insert(name, stat);
        removed += tasks
            .delete_many(doc! {"status":status})
            .await?
            .deleted_count;
    }
    body.push_str(&format!(
        "Deleted tasks: {removed}.\nTotal cycles: {cycles}.\n"
    ));
    settings
        .update_one(doc! {"setting":"tasks-stati"}, doc! {"$set":{"data":data}})
        .upsert(true)
        .await?;
    sender.send_text(&body, false, None).await?;
    Ok(Supply::Stop)
}

pub async fn public_channels(app: &App, sender: &Sender) -> Result<Vec<String>> {
    let mut ordered = Vec::new();
    for module in custom::public_modules(app)? {
        let (channel, _) = custom::identity(app, &module).await?;
        let channel = channel.as_str().ok_or(Error::Config)?;
        if !channel.contains('@') || ["@r_channels_test", "@r_channels"].contains(&channel) {
            continue;
        }
        let first = sender
            .db
            .collection::<Document>("urls")
            .find_one(doc! {"channel":channel.to_lowercase()})
            .sort(doc! {"ts":1})
            .await?
            .ok_or(Error::Config)?;
        ordered.push((
            first
                .get_datetime("ts")
                .map_err(|_| Error::Config)?
                .timestamp_millis(),
            channel.to_owned(),
        ));
    }
    let mut unique = HashMap::new();
    for (date, channel) in ordered {
        unique.insert(channel, date);
    }
    let mut ordered: Vec<_> = unique
        .into_iter()
        .map(|(channel, date)| (date, channel))
        .collect();
    ordered.sort_by_key(|(date, _)| *date);
    Ok(ordered.into_iter().map(|(_, c)| c).collect())
}
async fn first_members(
    stats: &mongodb::Collection<Document>,
    filter: Document,
    sort: Document,
) -> Result<f64> {
    let mut cursor = stats.find(filter).sort(sort).limit(100).await?;
    while let Some(record) = cursor.try_next().await? {
        if let Some(count) = model::numeric(&record, "members_cnt") {
            return Ok(count);
        }
    }
    Err(Error::Config)
}
pub async fn weekly(app: &App, sender: &Sender) -> Result<Supply> {
    let channels = public_channels(app, sender).await?;
    let mut new = Vec::new();
    let mut growers = Vec::new();
    let stats = app.db.collection::<Document>("stats");
    let cutoff = bson::DateTime::from_millis(Utc::now().timestamp_millis() - 7 * 86400 * 1000);
    for channel in &channels {
        let filter = doc! {"channel":channel.to_lowercase()};
        let first = stats
            .find_one(filter.clone())
            .sort(doc! {"ts":1})
            .await?
            .ok_or(Error::Config)?;
        let latest = stats
            .find_one(filter.clone())
            .sort(doc! {"ts":-1})
            .await?
            .ok_or(Error::Config)?;
        let first_date = first
            .get_datetime("ts")
            .map_err(|_| Error::Config)?
            .timestamp_millis();
        let last_date = latest
            .get_datetime("ts")
            .map_err(|_| Error::Config)?
            .timestamp_millis();
        if (last_date - first_date) / 86400000 <= 31 {
            new.push(channel.clone());
        }
        let previous = first_members(
            &stats,
            doc! {"channel":channel.to_lowercase(),"ts":{"$gte":cutoff}},
            doc! {"ts":1},
        )
        .await?;
        let current = first_members(&stats, filter, doc! {"ts":-1}).await?;
        let difference = current - previous;
        if difference >= 10. {
            growers.push((difference, channel.clone()));
        }
    }
    growers.sort_by(|a, b| b.0.total_cmp(&a.0));
    let growers: Vec<_> = growers.into_iter().take(3).map(|(_, c)| c).collect();
    let featured = channels
        .choose(&mut rand::thread_rng())
        .ok_or(Error::Config)?;
    let mut body = "<b>Weekend news</b>\n\n".to_owned();
    if !new.is_empty() {
        body.push_str(&format!(
            "🎉 Welcome to newly active channels: {}. 🎈🎈\n\n",
            new.join(", ")
        ));
    }
    body.push_str(&format!(
        "🏆 Channel of the week: {featured}. Join and enjoy!\n\n"
    ));
    if !growers.is_empty() {
        body.push_str(&format!(
            "🔥 Hottest channels of the week: {}.\n\n",
            growers.join(", ")
        ));
    }
    body.push_str("🙋\nQ: How can I help?\nA: Support us on Patreon and promote your favorite channels!\n\nQ: How to make similar channels?\nA: Ask at @r_channels or use manual at https://github.com/Fillll/reddit2telegram.\n\nQ: Where to donate?\nA: Patreon: https://www.patreon.com/reddit2telegram.");
    sender.send_text(&body, false, Some("HTML")).await?;
    tokio::time::sleep(Duration::from_secs(2)).await;
    for (index, page) in channels.chunks(100).enumerate() {
        let mut body = if index == 0 {
            "⬇️ All active channels:\n".into()
        } else {
            String::new()
        };
        body.push_str(
            &page
                .iter()
                .enumerate()
                .map(|(i, c)| format!("{:02}. {c}", index * 100 + i + 1))
                .collect::<Vec<_>>()
                .join("\n"),
        );
        sender.send_text(&body, false, None).await?;
        tokio::time::sleep(Duration::from_secs(2)).await;
    }
    Ok(Supply::Stop)
}

const HELP: &str = "Send channel data in one message:\nsubreddit: https://reddit.com/r/example\nchannel: @example_channel\ntags: #tag1 #tag2 #tag3\n\nOr send it step by step:\n1. subreddit\n2. channel\n3. tags\n\nCommands:\n/newchannel to restart\n/cancel to clear the current draft";
fn normalize(input: &str, kind: &str) -> String {
    let prefix = regex::Regex::new(&format!(r"(?i)^\s*{kind}\s*:\s*")).expect("literal regex");
    let value = prefix.replace(input.trim(), "");
    let pattern = if kind == "subreddit" {
        r"(?i)(?:https?://)?(?:www\.)?reddit\.com/r/([^/?#\s]+)"
    } else {
        r"(?i)(?:https?://)?(?:t(?:elegram)?\.me/)([^/?#\s]+)"
    };
    let regex = regex::Regex::new(pattern).expect("literal regex");
    let mut value = regex
        .captures(&value)
        .and_then(|c| c.get(1).map(|m| m.as_str().to_owned()))
        .unwrap_or_else(|| value.trim().trim_matches('/').to_owned());
    if kind == "subreddit" && value.to_lowercase().starts_with("r/") {
        value = value[2..].into();
    }
    if kind == "channel" {
        value = value.trim_start_matches('@').into();
    }
    if value.is_empty() || value.chars().any(char::is_whitespace) {
        String::new()
    } else {
        value.trim().trim_matches('/').into()
    }
}
fn normalize_tags(input: &str) -> String {
    let prefix = regex::Regex::new(r"(?i)^\s*tags\s*:\s*").expect("literal regex");
    let value = prefix.replace(input.trim(), "");
    let mut seen = BTreeSet::new();
    let mut tags = Vec::new();
    for part in value
        .split(|c: char| c.is_whitespace() || c == ',')
        .filter(|s| !s.is_empty())
    {
        let tag = if part.starts_with('#') {
            part.to_owned()
        } else {
            format!("#{}", part.trim_start_matches('#'))
        };
        if seen.insert(tag.clone()) {
            tags.push(tag);
        }
    }
    tags.join(" ")
}
fn complete_request(input: &str) -> Option<Value> {
    let mut lines: Vec<_> = input
        .lines()
        .map(str::trim)
        .filter(|l| !l.is_empty())
        .collect();
    if lines
        .first()
        .is_some_and(|l| ["/newchannel", "/start"].contains(&l.to_lowercase().as_str()))
    {
        lines.remove(0);
    }
    let mut result = json!({});
    for line in &lines {
        let low = line.to_lowercase();
        if low.starts_with("subreddit") {
            result["subreddit"] = json!(normalize(line, "subreddit"));
        } else if low.starts_with("channel") {
            result["channel"] = json!(normalize(line, "channel"));
        } else if low.starts_with("tags") {
            result["tags"] = json!(normalize_tags(line));
        }
    }
    if ["subreddit", "channel", "tags"]
        .iter()
        .all(|k| !text(&result, k).is_empty())
    {
        return Some(result);
    }
    if lines.len() == 3 {
        let result = json!({"subreddit":normalize(lines[0],"subreddit"),"channel":normalize(lines[1],"channel"),"tags":normalize_tags(lines[2])});
        if ["subreddit", "channel", "tags"]
            .iter()
            .all(|k| !text(&result, k).is_empty())
        {
            return Some(result);
        }
    }
    None
}
async fn reply(app: &App, sender: &Sender, user: i64, body: &str) -> Result<()> {
    app.sender(json!(user), sender.metrics.clone())
        .await?
        .send_text(body, false, None)
        .await?;
    Ok(())
}
async fn save_channel(app: &App, sender: &Sender, user: i64, data: &Value) -> Result<()> {
    let channels = app.db.collection::<Document>("channels");
    let channel = text(data, "channel");
    let subreddit = text(data, "subreddit");
    let tags = text(data, "tags");
    let existing = channels
        .find_one(doc! {"submodule":channel.to_lowercase()})
        .await?
        .is_some();
    channels.update_one(doc!{"submodule":channel.to_lowercase()},doc!{"$set":{"submodule":channel.to_lowercase(),"channel":format!("@{channel}"),"subreddit":subreddit,"tags":tags,"min_upvotes_limit":Bson::Null,"submissions_ranking":"hot","submissions_limit":100}}).upsert(true).await?;
    app.db
        .collection::<Document>("settings")
        .delete_one(doc! {"setting":format!("tech_receiver_state:{user}")})
        .await?;
    reply(
        app,
        sender,
        user,
        &format!(
            "{} channel:\nsubreddit: r/{subreddit}\nchannel: @{channel}\ntags: {tags}",
            if existing { "Updated" } else { "Saved" }
        ),
    )
    .await
}
async fn process_message(app: &App, sender: &Sender, user: i64, input: &str) -> Result<()> {
    let settings = app.db.collection::<Document>("settings");
    let setting = format!("tech_receiver_state:{user}");
    let low = input.trim().to_lowercase();
    if ["/help", "help"].contains(&low.as_str()) {
        return reply(app, sender, user, HELP).await;
    }
    if ["/cancel", "cancel"].contains(&low.as_str()) {
        settings.delete_one(doc! {"setting":&setting}).await?;
        return reply(app, sender, user, "Draft cleared.").await;
    }
    if ["/newchannel", "/start"].contains(&low.as_str()) {
        settings.delete_one(doc! {"setting":&setting}).await?;
        settings
            .update_one(
                doc! {"setting":&setting},
                doc! {"$set":{"data":{"step":"await_subreddit"}}},
            )
            .upsert(true)
            .await?;
        return reply(app, sender, user, "Send subreddit name or Reddit URL.").await;
    }
    if let Some(data) = complete_request(input) {
        return save_channel(app, sender, user, &data).await;
    }
    let previous = settings.find_one(doc! {"setting":&setting}).await?;
    let mut state = previous
        .and_then(|d| d.get_document("data").ok().cloned())
        .unwrap_or_else(|| doc! {"step":"await_subreddit"});
    let response = match state.get_str("step").unwrap_or("") {
        "await_subreddit" => {
            let subreddit = normalize(input, "subreddit");
            if subreddit.is_empty() {
                return reply(app, sender, user, HELP).await;
            }
            state = doc! {"step":"await_channel","subreddit":&subreddit};
            format!("Saved subreddit: r/{subreddit}\nNow send channel (@name or t.me link).")
        }
        "await_channel" => {
            let channel = normalize(input, "channel");
            if channel.is_empty() {
                return reply(
                    app,
                    sender,
                    user,
                    "Channel is invalid. Send @channel_name or https://t.me/channel_name",
                )
                .await;
            }
            state.insert("step", "await_tags");
            state.insert("channel", &channel);
            format!("Saved channel: @{channel}\nNow send tags like #tag1 #tag2 #tag3")
        }
        "await_tags" => {
            let tags = normalize_tags(input);
            if tags.is_empty() {
                return reply(
                    app,
                    sender,
                    user,
                    "Tags are invalid. Send tags like #tag1 #tag2 #tag3",
                )
                .await;
            }
            let data = json!({"channel":state.get_str("channel").map_err(|_|Error::Config)?,"subreddit":state.get_str("subreddit").map_err(|_|Error::Config)?,"tags":tags});
            return save_channel(app, sender, user, &data).await;
        }
        _ => {
            settings.delete_one(doc! {"setting":&setting}).await?;
            return reply(app, sender, user, HELP).await;
        }
    };
    settings
        .update_one(doc! {"setting":&setting}, doc! {"$set":{"data":state}})
        .upsert(true)
        .await?;
    reply(app, sender, user, &response).await
}
pub async fn receiver(app: &App, sender: &Sender) -> Result<Supply> {
    let settings = app.db.collection::<Document>("settings");
    settings
        .create_index(
            IndexModel::builder()
                .keys(doc! {"setting":1})
                .options(IndexOptions::builder().unique(true).build())
                .build(),
        )
        .await?;
    let record = settings.find_one(doc! {"setting":1}).await?;
    let mut last = record
        .as_ref()
        .and_then(|d| model::numeric(d, "last_update"))
        .unwrap_or(0.) as i64;
    if record.is_none() {
        settings
            .insert_one(doc! {"setting":1,"last_update":0})
            .await?;
    }
    let updates = sender.api("getUpdates", json!({"offset":last+1})).await?;
    let papa = app.config.values["telegram"]["papa"]
        .as_i64()
        .or_else(|| text(&app.config.values["telegram"], "papa").parse().ok())
        .ok_or(Error::Config)?;
    for update in updates.as_array().ok_or(Error::Telegram)? {
        last = last.max(update["update_id"].as_i64().ok_or(Error::Telegram)?);
        let message = &update["message"];
        let Some(user) = message["chat"]["id"].as_i64() else {
            continue;
        };
        let Some(body) = message["text"].as_str() else {
            continue;
        };
        if user < 0 {
            continue;
        }
        sender.api("forwardMessage",json!({"chat_id":app.config.dev_chat(),"from_chat_id":user,"message_id":message["message_id"]})).await?;
        if user == papa {
            process_message(app, sender, user, body).await?;
        }
    }
    settings
        .update_one(doc! {"setting":1}, doc! {"$set":{"last_update":last}})
        .await?;
    Ok(Supply::Stop)
}
