//! Subscriber snapshots and durable milestone delivery, sharing Python schemas.
use crate::{
    custom,
    durable::{self, AckMode, Checkpoint, Lease},
    model::{self, Error, Result, Supply, date, long_sleep, short_sleep},
    queue::App,
    reddit::Reddit,
    sender::Sender,
};
use futures_util::TryStreamExt;
use mongodb::{
    Collection,
    bson::{Document, doc},
};
use rand::seq::SliceRandom;
use serde_json::json;
use std::{collections::HashSet, sync::Arc};

const MAIN: &str = "@reddit2telegram";
const EVENT_KIND: &str = "r2t_achievement_delivery";
const HISTORY: &str = "r2t_achievements";
const LOCK: &str = "r2t_achievement_sweep_lock";

struct Milestones<'a> {
    app: &'a App,
    sender: &'a Sender,
    settings: Collection<Document>,
    lease: Lease,
}
impl Milestones<'_> {
    async fn queue(&self, module: &str, channel: &str, achievement: i64) -> Result<()> {
        let channel = channel.to_lowercase();
        if let Some(legacy) = self.settings.find_one(doc! {"setting":HISTORY}).await? {
            if let Some(channels) = legacy.get("channels") {
                let channels = channels.as_document().ok_or(Error::Config)?;
                if let Some(previous) = channels.get(&channel) {
                    let previous = previous.as_array().ok_or(Error::Config)?;
                    if previous
                        .iter()
                        .any(|v| durable::integer(v) == Some(achievement))
                    {
                        return Ok(());
                    }
                }
            }
        }
        let id = format!("{EVENT_KIND}:{channel}:{achievement}");
        self.settings.update_one(doc!{"_id":&id},doc!{"$setOnInsert":{"setting":id,"kind":EVENT_KIND,"submodule":module,"channel":channel,"achievement":achievement,"complete":false,"message_ids":[],"forwarded_ids":[],"created_at":date()}}).upsert(true).await?;
        Ok(())
    }
    async fn candidate(
        &self,
        event: &Document,
        checkpoint: Arc<Checkpoint>,
        posting_attempted: &mut bool,
    ) -> Result<()> {
        let module = event.get_str("submodule").map_err(|_| Error::Config)?;
        let source = custom::resolve(self.app, module).await?;
        let channel = event.get_str("channel").map_err(|_| Error::Config)?;
        let number = event
            .get("achievement")
            .and_then(durable::integer)
            .ok_or(Error::Config)?;
        let heading =
            format!("🏆 Great achievement!\n{channel}\n💪 Milestone of {number} subscribers.\n\n");
        let mut reddit = Reddit::new(self.app.config.clone(), self.sender.metrics.clone())?;
        let mut sender = self
            .app
            .sender(json!(MAIN), self.sender.metrics.clone())
            .await?;
        sender.acknowledgement = Some(checkpoint.clone());
        let mut scanned = 0;
        let mut after = None;
        'pages: while scanned < 1000 {
            let mut retries = 0;
            let page = loop {
                match reddit
                    .listing(&source.subreddit, "top", 1000, after.as_deref())
                    .await
                {
                    Ok(page) => break page,
                    Err(error) => {
                        retries += 1;
                        if retries >= 10 {
                            return Err(error);
                        }
                        self.sender.metrics.count("reddit_listing_retries", 1);
                        long_sleep(2.818281828 * std::f64::consts::PI / 2.).await;
                    }
                }
            };
            let items = page["data"]["children"].as_array().ok_or(Error::Reddit)?;
            if items.is_empty() {
                break;
            }
            for item in items {
                if scanned >= 1000 {
                    break;
                }
                scanned += 1;
                let submission = &item["data"];
                let link = format!("https://redd.it/{}", model::text(submission, "id"));
                if sender.was_before(&link).await? || sender.too_many_errors(&link).await? {
                    continue;
                }
                *posting_attempted = true;
                let mut result = custom::nice(
                    self.app,
                    module,
                    submission,
                    &sender,
                    &heading,
                    "",
                    Some(channel),
                    &mut reddit,
                )
                .await?;
                if !checkpoint.ids()?.is_empty() && result != Supply::Sent {
                    result = Supply::Stop;
                }
                match result {
                    Supply::Sent => {
                        sender.mark(&link, true).await?;
                        break 'pages;
                    }
                    Supply::Reject => sender.mark(&link, false).await?,
                    Supply::Skip => {}
                    Supply::Stop => break 'pages,
                }
            }
            after = page["data"]["after"].as_str().map(str::to_owned);
            if after.is_none() {
                break;
            }
        }
        Ok(())
    }
    async fn deliver(&self, event: &Document) -> Result<()> {
        self.lease.renew().await?;
        let id = event.get("_id").ok_or(Error::Config)?.clone();
        let selector = doc! {"_id":&id};
        self.settings
            .update_one(
                selector.clone(),
                doc! {"$inc":{"attempts":1},"$set":{"last_attempt_at":date()}},
            )
            .await?;
        let checkpoint = Checkpoint::new(
            self.settings.clone(),
            selector.clone(),
            AckMode::Achievement,
            durable::identifiers(event, "message_ids")?,
        );
        let channel = event.get_str("channel").map_err(|_| Error::Config)?;
        let number = event
            .get("achievement")
            .and_then(durable::integer)
            .ok_or(Error::Config)?;
        if checkpoint.ids()?.is_empty() {
            let mut posting_attempted = false;
            if let Err(error) = self
                .candidate(event, checkpoint.clone(), &mut posting_attempted)
                .await
            {
                if checkpoint.ids()?.is_empty() && posting_attempted {
                    return Err(error);
                }
            }
            if checkpoint.ids()?.is_empty() {
                let mut sender = self
                    .app
                    .sender(json!(MAIN), self.sender.metrics.clone())
                    .await?;
                sender.acknowledgement = Some(checkpoint.clone());
                let result=sender.send_text(&format!("🏆 Great achievement!\n{channel}\n💪 Milestone of {number} subscribers."),false,None).await?;
                if result != Supply::Sent || checkpoint.ids()?.is_empty() {
                    return Err(Error::Announcement);
                }
            }
        }
        self.lease.renew().await?;
        let ids = checkpoint.ids()?;
        self.settings
            .update_one(
                selector.clone(),
                doc! {"$addToSet":{"message_ids":{"$each":ids.clone()}}},
            )
            .await?;
        let mut history = Document::new();
        history.insert(format!("channels.{channel}"), number);
        self.settings
            .update_one(doc! {"setting":HISTORY}, doc! {"$addToSet":history})
            .upsert(true)
            .await?;
        if channel != MAIN {
            let forwarded = durable::identifiers(event, "forwarded_ids")?;
            let sender = self
                .app
                .sender(json!(channel), self.sender.metrics.clone())
                .await?;
            for id in ids {
                if forwarded.contains(&id) {
                    continue;
                }
                self.lease.renew().await?;
                sender
                    .api(
                        "forwardMessage",
                        json!({"chat_id":channel,"from_chat_id":MAIN,"message_id":id}),
                    )
                    .await?;
                self.settings
                    .update_one(selector.clone(), doc! {"$addToSet":{"forwarded_ids":id}})
                    .await?;
            }
        }
        self.settings
            .update_one(
                selector,
                doc! {"$set":{"complete":true,"completed_at":date()}},
            )
            .await?;
        Ok(())
    }
    async fn sweep(&self) -> Result<Supply> {
        report(self.sender, "Regular bypass started.", None).await;
        let thresholds: Vec<i64> = serde_json::from_str(include_str!("../assets/milestones.json"))?;
        let mut modules = custom::public_modules(self.app)?;
        let count = modules.len();
        let coefficient = 2000. / 3. / 2. / count.max(1) as f64;
        modules.shuffle(&mut rand::thread_rng());
        let mut seen = HashSet::new();
        let mut totals = Totals::default();
        let mut snapshots = Vec::new();
        let stats = self.app.db.collection::<Document>("stats");
        for module in modules {
            self.lease.renew().await?;
            short_sleep(coefficient).await;
            let channel = match custom::resolve(self.app, &module).await {
                Ok(channel) => {
                    let Some(channel) = channel.destination.as_str().map(str::to_owned) else {
                        continue;
                    };
                    if !channel.starts_with('@') || !seen.insert(channel.to_lowercase()) {
                        continue;
                    }
                    channel
                }
                Err(_) => {
                    totals.errors += 1;
                    continue;
                }
            };
            let mut snapshot =
                doc! {"channel":channel.to_lowercase(),"ts":date(),"submodule":&module};
            totals.channels += 1;
            let administrators: Result<Vec<String>> = async {
                let data = self
                    .sender
                    .api("getChatAdministrators", json!({"chat_id":&channel}))
                    .await?;
                let mut names = Vec::new();
                for admin in data.as_array().ok_or(Error::Telegram)? {
                    if let Some(name) = admin["user"]["username"].as_str() {
                        if name != "reddit2telegram_bot" {
                            names.push(format!("@{name}"));
                        }
                    } else {
                        names.push("%NO_USERNAME%".into());
                    }
                }
                Ok(names)
            }
            .await;
            match administrators {
                Ok(names) => {
                    totals.admins += names.len() as i64;
                    snapshot.insert("admins", names);
                }
                Err(_) => {
                    totals.errors += 1;
                    report(
                        self.sender,
                        &format!("Failed to get admins for {channel}."),
                        None,
                    )
                    .await;
                }
            }
            short_sleep(coefficient).await;
            let observation: Result<(i64, i64)> = async {
                let members = self
                    .sender
                    .api("getChatMemberCount", json!({"chat_id":&channel}))
                    .await?
                    .as_i64()
                    .ok_or(Error::Telegram)?;
                let previous = stats
                    .find_one(doc! {"channel":channel.to_lowercase(),"members_cnt":{"$gte":0}})
                    .sort(doc! {"ts":-1})
                    .await?;
                let before = if let Some(previous) = previous {
                    previous
                        .get("members_cnt")
                        .and_then(durable::integer)
                        .ok_or(Error::Config)?
                } else {
                    members
                };
                for threshold in &thresholds {
                    if before < *threshold && *threshold <= members {
                        self.queue(&module, &channel, *threshold).await?;
                    }
                }
                snapshot.insert("members_cnt", members);
                stats.insert_one(snapshot).await?;
                Ok((before, members))
            }
            .await;
            match observation {
                Ok((before, current)) => {
                    totals.members += current;
                    totals.previous += before;
                    snapshots.push(Snapshot {
                        channel,
                        before,
                        current,
                    });
                }
                Err(_) => {
                    totals.errors += 1;
                    report(
                        self.sender,
                        &format!("Failed to collect statistics or queue milestones for {channel}."),
                        None,
                    )
                    .await;
                }
            }
        }
        let mut pending = self
            .settings
            .find(doc! {"kind":EVENT_KIND,"complete":false})
            .await?;
        while let Some(event) = pending.try_next().await? {
            self.lease.renew().await?;
            if let Err(error) = self.deliver(&event).await {
                totals.errors += 1;
                self.settings.update_one(doc!{"_id":event.get("_id").ok_or(Error::Config)?.clone()},doc!{"$set":{"last_error_type":error.to_string(),"last_failure_at":date()}}).await?;
                let channel = event.get_str("channel").map_err(|_| Error::Config)?;
                let number = event
                    .get("achievement")
                    .and_then(durable::integer)
                    .ok_or(Error::Config)?;
                report(
                    self.sender,
                    &format!("Milestone delivery pending: {channel}, {number} subscribers."),
                    None,
                )
                .await;
            }
        }
        let difference = totals.members - totals.previous;
        let sign = sign(difference);
        let percentage = if totals.previous != 0 {
            round2(difference as f64 / totals.previous as f64 * 100.)
        } else {
            "0".into()
        };
        let body = format!(
            "Ok, regular bypass results.\n\n<pre>Active channels: {}.</pre>\n<pre>Subscribers: {}.</pre>\n<pre>Cnt diff: {sign}{difference} ({sign}{percentage}%).</pre>\n<pre>Admins: {}.</pre>\n<pre>Errors during bypass: {}.</pre>\n\n<i>See you!</i>",
            totals.channels, totals.members, totals.admins, totals.errors
        );
        report(self.sender, &body, Some("HTML")).await;
        short_sleep(1.).await;
        snapshots.sort_by_key(|s| std::cmp::Reverse(s.current - s.before));
        report(
            self.sender,
            &leaderboard("📈 <b>TOP 5 GAIN</b> 📈\n", &snapshots),
            Some("HTML"),
        )
        .await;
        short_sleep(1.).await;
        snapshots.sort_by_key(|s| s.current - s.before);
        report(
            self.sender,
            &leaderboard("📉 <b>TOP 5 FALL</b> 📉\n", &snapshots),
            Some("HTML"),
        )
        .await;
        Ok(Supply::Stop)
    }
}
#[derive(Default)]
struct Totals {
    channels: i64,
    members: i64,
    admins: i64,
    errors: i64,
    previous: i64,
}
struct Snapshot {
    channel: String,
    before: i64,
    current: i64,
}
fn sign(value: i64) -> &'static str {
    if value < 0 {
        ""
    } else if value == 0 {
        "±"
    } else {
        "+"
    }
}
fn round2(value: f64) -> String {
    let text = format!("{value:.2}");
    let mut text = text.trim_end_matches('0').to_owned();
    if text.ends_with('.') {
        text.push('0');
    }
    text
}
fn leaderboard(heading: &str, snapshots: &[Snapshot]) -> String {
    let mut body = heading.to_owned();
    for record in snapshots.iter().take(5) {
        let difference = record.current - record.before;
        let sign = sign(difference);
        let percentage = if record.before != 0 {
            round2(difference as f64 / record.before as f64 * 100.)
        } else {
            "0".into()
        };
        body.push_str(&format!(
            "{}: {} {sign}{difference} ({sign}{percentage}%) → {}\n",
            record.channel, record.before, record.current
        ));
    }
    body
}
async fn report(sender: &Sender, body: &str, parse: Option<&str>) {
    let _ = sender.send_text(body, false, parse).await;
}
pub async fn run(app: &App, sender: &Sender) -> Result<Supply> {
    let settings = app.db.collection::<Document>("settings");
    let mut lease = Lease::new(settings.clone(), LOCK);
    if !lease.acquire().await? {
        return Ok(Supply::Stop);
    }
    let sweep = Milestones {
        app,
        sender,
        settings,
        lease,
    };
    let outcome = sweep.sweep().await;
    let released = sweep.lease.release().await;
    outcome.and_then(|result| released.map(|_| result))
}
