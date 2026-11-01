//! Stable anniversary inventory, frozen messages and resumable delivery.
use crate::{
    custom,
    durable::{AckMode, Checkpoint, Lease},
    model::{Error, Result, Supply, date, short_sleep},
    queue::App,
    sender::{AckSink, Sender},
};
use chrono::{Datelike, NaiveDate, TimeZone, Utc};
use futures_util::TryStreamExt;
use mongodb::{
    Collection,
    bson::{self, Bson, Document, doc},
};
use serde_json::Value;
use std::collections::{BTreeSet, HashSet};

const DATE_KIND: &str = "r2t_anniversary_date";
const EVENT_KIND: &str = "r2t_anniversary_delivery";
const RUN_KIND: &str = "r2t_anniversary_run";
const LOCK: &str = "r2t_anniversary_sweep_lock";
const MAIN: &str = "@reddit2telegram";
const COMMUNITY: &str = "@r_channels";

fn utc_date(value: &Bson) -> Result<NaiveDate> {
    match value {
        Bson::DateTime(date) => Utc
            .timestamp_millis_opt(date.timestamp_millis())
            .single()
            .map(|d| d.date_naive())
            .ok_or(Error::Config),
        Bson::String(value) => {
            NaiveDate::parse_from_str(value, "%Y-%m-%d").map_err(|_| Error::Config)
        }
        _ => Err(Error::Config),
    }
}
fn midnight(date: NaiveDate) -> Result<bson::DateTime> {
    Ok(bson::DateTime::from_millis(
        date.and_hms_opt(0, 0, 0)
            .ok_or(Error::Config)?
            .and_utc()
            .timestamp_millis(),
    ))
}
fn escape(value: &str) -> String {
    value
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&#x27;")
}
fn chat_key(value: &Value) -> String {
    value
        .as_str()
        .map(str::to_lowercase)
        .unwrap_or_else(|| value.to_string())
}
fn bump(record: &mut Document, key: &str) {
    let n = record
        .get(key)
        .and_then(crate::durable::integer)
        .unwrap_or(0);
    record.insert(key, n + 1);
}
fn push_error(record: &mut Document, error: Document) {
    if let Ok(errors) = record.get_array_mut("errors") {
        errors.push(Bson::Document(error));
    }
}

pub fn messages(channel: &str, years: i32, channels: &[String], today: NaiveDate) -> Vec<String> {
    let plural = if years == 1 { "" } else { "s" };
    let mut intro = format!(
        "🌍 <b>Discover the Reddit2Telegram family</b>\n\n📣 @reddit2telegram — our main channel for discovering posts and channels from across the network.\n\n💬 @r_channels — join the community, find new channels, ask questions, and suggest your next favorite.\n\n🎂 <b>Celebrating {}: {years} year{plural} together!</b>\n📅 {}\nThank you for reading, sharing, and being part of the community. Here’s to another year of great discoveries!",
        escape(channel),
        today.format("%d %B %Y")
    );
    let others: BTreeSet<_> = channels
        .iter()
        .map(|c| c.to_lowercase())
        .filter(|c| {
            ![
                channel.to_lowercase(),
                MAIN.into(),
                COMMUNITY.into(),
                "@r_channels_test".into(),
            ]
            .contains(c)
        })
        .collect();
    if others.is_empty() {
        return vec![intro];
    }
    intro.push_str("\n\n🧭 Explore more of our channels in the directory below.");
    let mut pages = Vec::new();
    let mut lines: Vec<String> = Vec::new();
    for (number, channel) in others.iter().enumerate() {
        let line = format!("{}. {}", number + 1, escape(channel));
        let candidate = if lines.is_empty() {
            line.clone()
        } else {
            lines.join("\n") + "\n" + &line
        };
        if !lines.is_empty() && (lines.len() == 100 || candidate.encode_utf16().count() > 3400) {
            pages.push(lines.join("\n"));
            lines.clear();
        }
        lines.push(line);
    }
    if !lines.is_empty() {
        pages.push(lines.join("\n"));
    }
    let total = pages.len();
    let mut result = vec![intro];
    result.extend(
        pages
            .into_iter()
            .enumerate()
            .map(|(i, page)| format!("🧭 <b>More channels · {}/{total}</b>\n\n{page}", i + 1)),
    );
    result
}

struct Anniversary<'a> {
    app: &'a App,
    sender: &'a Sender,
    settings: Collection<Document>,
    lease: Lease,
}
impl Anniversary<'_> {
    async fn birthday(
        &self,
        channel: &str,
        record: Option<&Document>,
    ) -> Result<Option<NaiveDate>> {
        let id = format!("{DATE_KIND}:{channel}");
        let cached = self.settings.find_one(doc! {"_id":&id}).await?;
        let explicit = record
            .and_then(|d| d.get("anniversary_date"))
            .filter(|v| !matches!(v, Bson::Null));
        let (birthday, source) = if let Some(explicit) = explicit {
            (utc_date(explicit)?, "explicit")
        } else if let Some(cached) = cached {
            return Ok(Some(utc_date(cached.get("date").ok_or(Error::Config)?)?));
        } else {
            let first = self
                .app
                .db
                .collection::<Document>("urls")
                .find_one(doc! {"channel":channel,"sent":true,"ts":{"$type":"date"}})
                .sort(doc! {"ts":1})
                .projection(doc! {"ts":1})
                .await?;
            let Some(first) = first else {
                return Ok(None);
            };
            (
                utc_date(first.get("ts").ok_or(Error::Config)?)?,
                "first_sent_post",
            )
        };
        let values = doc! {"setting":&id,"kind":DATE_KIND,"channel":channel,"date":midnight(birthday)?,"source":source};
        let mut update = Document::new();
        update.insert(
            if explicit.is_some() {
                "$set"
            } else {
                "$setOnInsert"
            },
            values,
        );
        self.settings
            .update_one(doc! {"_id":id}, update)
            .upsert(true)
            .await?;
        Ok(Some(birthday))
    }
    async fn inventory(&self) -> Result<(Vec<(String, NaiveDate)>, Vec<String>, Vec<Document>)> {
        let handles =
            regex::Regex::new(r"^@[a-zA-Z][a-zA-Z0-9_]{4,31}$").map_err(|_| Error::Config)?;
        let local: Value = serde_json::from_str(include_str!("../assets/local_channels.json"))?;
        let mut channels = Vec::new();
        let mut seen = HashSet::new();
        let mut skipped = Vec::new();
        let mut errors = Vec::new();
        for module in custom::public_modules(self.app)? {
            self.lease.renew().await?;
            let item: Result<Option<(String, Option<NaiveDate>)>> = async {
                let record = self
                    .app
                    .db
                    .collection::<Document>("channels")
                    .find_one(doc! {"submodule":&module})
                    .await?;
                let channel = if let Some(record) = &record {
                    record.get_str("channel").ok().map(str::to_owned)
                } else {
                    local[&module]["t_channel"].as_str().map(str::to_owned)
                };
                let Some(channel) = channel else {
                    if record.is_none() {
                        return Err(Error::Config);
                    }
                    return Ok(None);
                };
                if !handles.is_match(&channel) {
                    return Ok(None);
                }
                let channel = channel.to_lowercase();
                if [COMMUNITY, "@r_channels_test"].contains(&channel.as_str())
                    || seen.contains(&channel)
                {
                    return Ok(None);
                }
                let birthday = self.birthday(&channel, record.as_ref()).await?;
                Ok(Some((channel, birthday)))
            }
            .await;
            match item {
                Ok(Some((channel, Some(birthday)))) => {
                    seen.insert(channel.clone());
                    channels.push((channel, birthday));
                }
                Ok(Some((channel, None))) => skipped.push(channel),
                Ok(None) => {}
                Err(error) => errors.push(doc! {"submodule":module,"error_type":error.to_string()}),
            }
        }
        Ok((channels, skipped, errors))
    }
    async fn queue(
        &self,
        channel: &str,
        years: i32,
        today: NaiveDate,
        channels: &[String],
    ) -> Result<()> {
        let id = format!("{EVENT_KIND}:{channel}:{}", today.year());
        let plural = if years == 1 { "" } else { "s" };
        let notice = format!(
            "🎂 <b>Celebrating {}: {years} year{plural} together!</b>\n📅 {}\n\nDiscover this channel and more in our main feed @reddit2telegram.\nJoin @r_channels to explore the network and meet the community.",
            escape(channel),
            today.format("%d %B %Y")
        );
        let mut deliveries: Vec<Document> = messages(channel, years, channels, today)
            .into_iter()
            .map(|body| doc! {"destination":channel,"text":body,"state":"pending"})
            .collect();
        let mut destinations = HashSet::from([channel.to_lowercase()]);
        for destination in [
            Value::String(MAIN.into()),
            Value::String(COMMUNITY.into()),
            self.app.config.dev_chat(),
        ] {
            if !destinations.insert(chat_key(&destination)) {
                continue;
            }
            deliveries.push(doc!{"destination":bson::to_bson(&destination).map_err(|_|Error::Config)?,"text":&notice,"state":"pending"});
        }
        self.settings.update_one(doc!{"_id":&id},doc!{"$setOnInsert":{"setting":id,"kind":EVENT_KIND,"channel":channel,"year":today.year(),"years":years,"anniversary":today.to_string(),"created_at":date(),"complete":false,"deliveries":deliveries}}).upsert(true).await?;
        Ok(())
    }
    async fn deliver(&self, event: &Document) -> Result<bool> {
        let mut blocked = HashSet::new();
        let id = event.get("_id").ok_or(Error::Config)?.clone();
        let deliveries = event.get_array("deliveries").map_err(|_| Error::Config)?;
        for (index, delivery) in deliveries.iter().enumerate() {
            self.lease.renew().await?;
            let delivery = delivery.as_document().ok_or(Error::Config)?;
            let destination: Value =
                bson::from_bson(delivery.get("destination").ok_or(Error::Config)?.clone())
                    .map_err(|_| Error::Config)?;
            let blocked_key = destination.to_string();
            let state = delivery.get_str("state").map_err(|_| Error::Config)?;
            let path = format!("deliveries.{index}");
            if state == "sent" || blocked.contains(&blocked_key) {
                continue;
            }
            if ["sending", "uncertain"].contains(&state) {
                let mut selector = doc! {"_id":&id};
                selector.insert(format!("{path}.state"), "sending");
                let mut values = Document::new();
                values.insert(format!("{path}.state"), "uncertain");
                self.settings
                    .update_one(selector, doc! {"$set":values})
                    .await?;
                blocked.insert(blocked_key);
                continue;
            }
            let attempt = uuid::Uuid::new_v4().simple().to_string();
            let mut selector = doc! {"_id":&id};
            selector.insert(format!("{path}.state"), "pending");
            let mut values = Document::new();
            values.insert(format!("{path}.state"), "sending");
            values.insert(format!("{path}.attempt"), &attempt);
            values.insert(format!("{path}.attempted_at"), date());
            let mut increments = Document::new();
            increments.insert(format!("{path}.attempts"), 1);
            if self
                .settings
                .update_one(selector, doc! {"$set":values,"$inc":increments})
                .await?
                .matched_count
                == 0
            {
                blocked.insert(blocked_key);
                continue;
            }
            let mut selector = doc! {"_id":&id};
            selector.insert(format!("{path}.attempt"), &attempt);
            let checkpoint = Checkpoint::new(
                self.settings.clone(),
                selector.clone(),
                AckMode::Anniversary { path: path.clone() },
                vec![],
            );
            let mut sender = self.sender.clone();
            sender.destination = destination;
            sender.acknowledgement = Some(checkpoint.clone());
            let outcome: Result<()> = async {
                if sender
                    .send_text(
                        delivery.get_str("text").map_err(|_| Error::Config)?,
                        true,
                        Some("HTML"),
                    )
                    .await?
                    != Supply::Sent
                    || checkpoint.ids()?.is_empty()
                {
                    return Err(Error::Announcement);
                }
                Ok(())
            }
            .await;
            if let Err(error) = outcome {
                if !checkpoint.ids()?.is_empty() {
                    checkpoint.record(vec![]).await?;
                } else {
                    let retryable =
                        matches!(error, Error::Rejected | Error::Forbidden | Error::RateLimit);
                    let mut values = Document::new();
                    values.insert(
                        format!("{path}.state"),
                        if retryable { "pending" } else { "uncertain" },
                    );
                    values.insert(format!("{path}.last_error_type"), error.to_string());
                    self.settings
                        .update_one(selector, doc! {"$set":values})
                        .await?;
                }
                blocked.insert(blocked_key);
            }
            short_sleep(1.).await;
        }
        let current = self
            .settings
            .find_one(doc! {"_id":&id})
            .await?
            .ok_or(Error::Database)?;
        let complete = current
            .get_array("deliveries")
            .map_err(|_| Error::Config)?
            .iter()
            .all(|part| part.as_document().and_then(|d| d.get_str("state").ok()) == Some("sent"));
        self.settings
            .update_one(
                doc! {"_id":id},
                doc! {"$set":{"complete":complete,"updated_at":date()}},
            )
            .await?;
        Ok(complete)
    }
    async fn sweep(&mut self, run: &mut Document, acquired: &mut bool) -> Result<()> {
        *acquired = self.lease.acquire().await?;
        if !*acquired {
            run.insert("status", "skipped_overlap");
            return Ok(());
        }
        if let Some(previous) = &self.lease.previous_owner {
            self.settings.update_many(doc!{"kind":RUN_KIND,"owner":previous,"status":"running","_id":{"$ne":run.get("_id").ok_or(Error::Config)?.clone()}},doc!{"$set":{"status":"interrupted","finished_at":date(),"errors":[{"error_type":"InterruptedSweep"}]}}).await?;
        }
        let (channels, skipped, errors) = self.inventory().await?;
        let names: Vec<_> = channels
            .iter()
            .map(|(channel, _)| channel.clone())
            .collect();
        run.insert("channels", channels.len() as i64);
        run.insert("skipped_no_history", skipped);
        run.insert("errors", errors);
        let today =
            NaiveDate::parse_from_str(run.get_str("date").map_err(|_| Error::Config)?, "%Y-%m-%d")
                .map_err(|_| Error::Config)?;
        for (channel, birthday) in &channels {
            self.lease.renew().await?;
            let mut month = birthday.month();
            let mut day = birthday.day();
            if month == 2 && day == 29 && NaiveDate::from_ymd_opt(today.year(), 2, 29).is_none() {
                month = 2;
                day = 28;
            }
            let years = today.year() - birthday.year();
            if years > 0 && (today.month(), today.day()) == (month, day) {
                bump(run, "due");
                self.queue(channel, years, today, &names).await?;
            }
        }
        let mut pending = self
            .settings
            .find(doc! {"kind":EVENT_KIND,"complete":false})
            .batch_size(25)
            .await?;
        while let Some(event) = pending.try_next().await? {
            self.lease.renew().await?;
            let channel = event.get_str("channel").map_err(|_| Error::Config)?;
            if !names.iter().any(|c| c == channel) {
                continue;
            }
            match self.deliver(&event).await {
                Ok(true) => bump(run, "completed"),
                Ok(false) => {}
                Err(error) => push_error(
                    run,
                    doc! {"event":event.get("_id").ok_or(Error::Config)?.clone(),"error_type":error.to_string()},
                ),
            }
        }
        let mut pending = self
            .settings
            .find(doc! {"kind":EVENT_KIND,"complete":false})
            .batch_size(25)
            .await?;
        while let Some(event) = pending.try_next().await? {
            bump(run, "pending");
            for part in event.get_array("deliveries").map_err(|_| Error::Config)? {
                if part
                    .as_document()
                    .and_then(|d| d.get_str("state").ok())
                    .is_some_and(|s| ["sending", "uncertain"].contains(&s))
                {
                    bump(run, "uncertain_messages");
                }
            }
        }
        let partial = run
            .get("pending")
            .and_then(crate::durable::integer)
            .unwrap_or(0)
            > 0
            || !run
                .get_array("errors")
                .map_err(|_| Error::Config)?
                .is_empty();
        run.insert("status", if partial { "partial" } else { "success" });
        Ok(())
    }
}
pub async fn run(app: &App, sender: &Sender) -> Result<Supply> {
    let settings = app.db.collection::<Document>("settings");
    let lease = Lease::new(settings.clone(), LOCK);
    let run_id = format!("{RUN_KIND}:{}", uuid::Uuid::new_v4().simple());
    let mut run = doc! {"_id":&run_id,"kind":RUN_KIND,"setting":&run_id,"owner":&lease.owner,"date":Utc::now().date_naive().to_string(),"started_at":date(),"status":"running","channels":0,"due":0,"completed":0,"pending":0,"uncertain_messages":0,"skipped_no_history":[],"errors":[]};
    settings.insert_one(run.clone()).await?;
    let mut anniversary = Anniversary {
        app,
        sender,
        settings: settings.clone(),
        lease,
    };
    let mut acquired = false;
    let result = anniversary.sweep(&mut run, &mut acquired).await;
    if let Err(error) = result {
        run.insert("status", "failed");
        push_error(&mut run, doc! {"error_type":error.to_string()});
    }
    run.insert("finished_at", date());
    let mut values = run.clone();
    values.remove("_id");
    let stored = settings
        .update_one(doc! {"_id":&run_id}, doc! {"$set":values})
        .await
        .map(|_| ())
        .map_err(Error::from);
    let released = if acquired {
        anniversary.lease.release().await
    } else {
        Ok(())
    };
    result.and(stored).and(released)?;
    if matches!(run.get_str("status"), Ok("failed" | "partial")) {
        return Err(Error::Announcement);
    }
    Ok(Supply::Stop)
}
