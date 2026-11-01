use crate::{
    custom,
    http::Http,
    metrics::{self, Metrics},
    model::{self, Config, Error, Result, Supply, now},
    reddit::Reddit,
    sender::{self, Sender},
};
use chrono::{Datelike, Local, Timelike};
use mongodb::{
    Database,
    bson::{Bson, Document, doc},
    options::ReturnDocument,
};
use rand::seq::SliceRandom;
use serde_json::json;
use std::{path::Path, sync::Arc, time::Duration};
use tokio::{sync::Semaphore, task::JoinSet};

#[derive(Clone)]
pub struct App {
    pub config: Arc<Config>,
    pub db: Database,
    pub videos: Arc<Semaphore>,
}
impl App {
    pub async fn load(path: &Path) -> Result<Self> {
        let config = Arc::new(Config::load(path)?);
        #[cfg(all(target_os = "linux", target_env = "gnu"))]
        unsafe {
            libc::mallopt(
                libc::M_ARENA_MAX,
                config.values["pool"]["malloc_arenas"].as_i64().unwrap_or(4) as i32,
            );
        }
        let db = config.database().await?;
        Ok(Self {
            config,
            db,
            videos: Arc::new(Semaphore::new(2)),
        })
    }
    pub async fn sender(&self, destination: serde_json::Value, metrics: Metrics) -> Result<Sender> {
        Sender::new(
            self.config.clone(),
            self.db.clone(),
            destination,
            metrics,
            self.videos.clone(),
        )
        .await
    }
    pub async fn run_job(&self, task: Document) -> Result<()> {
        let id = task.get("_id").ok_or(Error::Config)?.clone();
        let task_id = match &id {
            Bson::ObjectId(id) => id.to_hex(),
            other => other.to_string(),
        };
        let args = task.get_document("args").map_err(|_| Error::Config)?;
        let module = args.get_str("submodule_name").unwrap_or("");
        let metrics = Metrics::begin(
            &self.config.root,
            &task_id,
            module,
            model::numeric(&task, "created_at"),
        );
        let tasks = self.db.collection::<Document>("tasks");
        let result: Result<()> = async {
            tasks
                .update_one(
                    doc! {"_id":&id},
                    doc! {"$set":{"status":2,"updated_at":now()}},
                )
                .await?;
            if task.get_str("name").unwrap_or("") != "supply" {
                return Err(Error::UnknownTask);
            }
            let config = if let Ok(config) = args.get_document("config") {
                let mut next = (*self.config).clone();
                next.values = model::json_doc(config.clone())?;
                Arc::new(next)
            } else if let Ok(path) = args.get_str("config_filename") {
                Arc::new(Config::load(Path::new(path))?)
            } else {
                self.config.clone()
            };
            let db = if config.values["db"] == self.config.values["db"] {
                self.db.clone()
            } else {
                config.database().await?
            };
            let job = Self {
                config,
                db,
                videos: self.videos.clone(),
            };
            job.supply(module, metrics.clone()).await
        }
        .await;
        let stored = tasks
            .update_one(
                doc! {"_id":&id},
                doc! {"$set":{"status":if result.is_ok(){3}else{4},"updated_at":now()}},
            )
            .await;
        let result = result.and(stored.map(|_| ()).map_err(Error::from));
        metrics.finish(result);
        if let Err(error) = result {
            eprintln!("task {task_id}: {error}");
        }
        result
    }
    pub async fn supply(&self, module: &str, metrics: Metrics) -> Result<()> {
        model::long_sleep(0.2).await;
        let channel = custom::resolve(self, module).await?;
        if !channel.requires_submission {
            let sender = self.sender(channel.destination.clone(), metrics).await?;
            custom::maintenance(self, module, &sender).await?;
            return Ok(());
        }
        let rankings = if let Some(rank) = &channel.ranking {
            vec![rank.as_str()]
        } else {
            vec!["hot", "new", "top"]
        };
        for ranking in rankings {
            let mut reddit = Reddit::new(self.config.clone(), metrics.clone())?;
            let sender = self
                .sender(channel.destination.clone(), metrics.clone())
                .await?;
            let mut after = None;
            let mut scanned = 0;
            let mut last = None;
            'listing: while scanned < channel.limit {
                let mut retries = 0;
                let page = loop {
                    match reddit
                        .listing(&channel.subreddit, ranking, channel.limit, after.as_deref())
                        .await
                    {
                        Ok(page) => break page,
                        Err(error) => {
                            retries += 1;
                            if retries >= 10 {
                                return Err(error);
                            }
                            metrics.count("reddit_listing_retries", 1);
                            model::long_sleep(2.818281828 * std::f64::consts::PI / 2.).await;
                        }
                    }
                };
                let items = page["data"]["children"].as_array().ok_or(Error::Reddit)?;
                if items.is_empty() {
                    break;
                }
                for item in items {
                    if scanned >= channel.limit {
                        break;
                    }
                    scanned += 1;
                    let submission = &item["data"];
                    let link = format!("https://redd.it/{}", model::text(submission, "id"));
                    if sender.was_before(&link).await? || sender.too_many_errors(&link).await? {
                        continue;
                    }
                    let result = custom::post(self, module, &channel, submission, &sender).await?;
                    last = Some(result);
                    match result {
                        Supply::Sent => {
                            sender.mark(&link, true).await?;
                            break 'listing;
                        }
                        Supply::Reject => sender.mark(&link, false).await?,
                        Supply::Skip => {}
                        Supply::Stop => break 'listing,
                    }
                }
                after = page["data"]["after"].as_str().map(str::to_owned);
                if after.is_none() {
                    break;
                }
            }
            // Python's identity test `success is False` retries only when no
            // candidate actually reached send_post, not after rejected/skipped ones.
            if last.is_some() {
                break;
            }
        }
        sender::clean(
            &self.config,
            Some(&channel.destination.as_str().unwrap_or("").to_owned()),
        )
        .await?;
        Ok(())
    }
}

pub async fn consumer(app: App) -> Result<()> {
    if app.config.worker_size() == 0
        || app.config.max_pending() == 0
        || app.config.batch_size() == 0
    {
        return Err(Error::Config);
    }
    let tasks = app.db.collection::<Document>("tasks");
    tasks
        .update_many(
            doc! {"status":{"$in":[2,5]},"updated_at":{"$lt":now()-60.}},
            doc! {"$set":{"status":1,"updated_at":now()}},
        )
        .await?;
    let workers = Arc::new(Semaphore::new(app.config.worker_size()));
    let mut pending = JoinSet::new();
    let mut terminate = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())?;
    let mut interrupt = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::interrupt())?;
    loop {
        while pending.try_join_next().is_some() {}
        tasks
            .update_many(
                doc! {"status":1,"created_at":{"$lt":now()-25.*60.}},
                doc! {"$set":{"status":4,"updated_at":now()}},
            )
            .await?;
        let available = app.config.max_pending().saturating_sub(pending.len());
        for _ in 0..available.min(app.config.batch_size()) {
            let claimed = tasks
                .find_one_and_update(
                    doc! {"status":1,"created_at":{"$gte":now()-25.*60.}},
                    doc! {"$set":{"status":5,"updated_at":now()}},
                )
                .sort(doc! {"created_at":1})
                .projection(doc! {"name":1,"args":1,"created_at":1})
                .return_document(ReturnDocument::After)
                .await?;
            let Some(task) = claimed else {
                break;
            };
            let app = app.clone();
            let workers = workers.clone();
            pending.spawn(async move {
                let _permit = workers.acquire_owned().await.map_err(|_| Error::Config)?;
                app.run_job(task).await
            });
        }
        tokio::select! {_=terminate.recv()=>break,_=interrupt.recv()=>break,_=tokio::time::sleep(Duration::from_secs(5))=>{}}
    }
    eprintln!("draining {} pending jobs", pending.len());
    while pending.join_next().await.is_some() {}
    Ok(())
}

pub fn schedules(config: &Config) -> Result<Vec<(String, String)>> {
    let mut reader = csv::ReaderBuilder::new()
        .delimiter(b'\t')
        .flexible(true)
        .from_path(config.cron_path())
        .map_err(|_| Error::Config)?;
    let mut rows = Vec::new();
    for row in reader.records() {
        let row = row.map_err(|_| Error::Config)?;
        rows.push((
            row.get(0).ok_or(Error::Config)?.into(),
            row.get(1).ok_or(Error::Config)?.into(),
        ));
    }
    Ok(rows)
}
pub async fn scheduler(app: App) -> Result<()> {
    let current = Local::now();
    let mut modules = Vec::new();
    for (mask, module) in schedules(&app.config)? {
        if cron_matches(&mask, current)? {
            modules.push(module);
        }
    }
    modules.shuffle(&mut rand::thread_rng());
    if modules.is_empty() {
        return Ok(());
    }
    let created = now();
    let count = modules.len();
    let docs:Vec<_>=modules.iter().map(|module|doc!{"name":"supply","args":{"submodule_name":module,"config_filename":app.config.path.to_string_lossy().as_ref()},"status":1,"created_at":created,"updated_at":created}).collect();
    app.db
        .collection::<Document>("tasks")
        .insert_many(docs)
        .await?;
    if let Some(run) = metrics::active(&app.config.root) {
        metrics::emit(&run, "scheduler_submitted", json!({"submitted_jobs":count}));
    }
    eprintln!("inserted {count} scheduled tasks");
    Ok(())
}

fn cron_matches(mask: &str, date: chrono::DateTime<Local>) -> Result<bool> {
    let parts: Vec<_> = mask.split_whitespace().collect();
    if parts.len() != 5 {
        return Err(Error::Config);
    }
    let minute = field(parts[0], date.minute(), 0, 59)?;
    let hour = field(parts[1], date.hour(), 0, 23)?;
    let day = field(parts[2], date.day(), 1, 31)?;
    let month = field(parts[3], date.month(), 1, 12)?;
    let weekday = field(parts[4], date.weekday().num_days_from_sunday(), 0, 7)?;
    let calendar = if parts[2] != "*" && parts[4] != "*" {
        day || weekday
    } else {
        day && weekday
    };
    Ok(minute && hour && month && calendar)
}
fn field(expression: &str, current: u32, min: u32, max: u32) -> Result<bool> {
    let parse = |s: &str| -> Result<u32> {
        match s.to_ascii_lowercase().as_str() {
            "sun" => Ok(0),
            "mon" => Ok(1),
            "tue" => Ok(2),
            "wed" => Ok(3),
            "thu" => Ok(4),
            "fri" => Ok(5),
            "sat" => Ok(6),
            _ => s.parse().map_err(|_| Error::Config),
        }
    };
    let mut matches = false;
    for item in expression.split(',') {
        let (range, step) = if let Some((range, step)) = item.split_once('/') {
            (range, parse(step)?)
        } else {
            (item, 1)
        };
        if step == 0 {
            return Err(Error::Config);
        }
        let (start, end) = if range == "*" {
            (min, max)
        } else if let Some((a, b)) = range.split_once('-') {
            (parse(a)?, parse(b)?)
        } else {
            let n = parse(range)?;
            (n, if item.contains('/') { max } else { n })
        };
        if start < min || end > max || start > end {
            return Err(Error::Config);
        }
        matches |= (start..=end)
            .step_by(step as usize)
            .any(|n| n == current || (max == 7 && n == 7 && current == 0));
    }
    Ok(matches)
}
