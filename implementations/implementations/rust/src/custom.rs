//! Native channel policies. Deployment stays disabled until the durable
//! achievement/anniversary state machines have also been ported and reviewed.
use crate::{
    maintenance,
    model::{self, Error, Result, Supply},
    queue::{self, App},
    sender::Sender,
};
use chrono::{Datelike, Local, TimeZone, Timelike, Utc};
use mongodb::bson::{Bson, Document, doc};
use rand::{Rng, seq::SliceRandom};
use serde_json::{Value, json};
use sha1::{Digest, Sha1};
use std::{collections::BTreeSet, sync::OnceLock};
use tokio::sync::OnceCell;

pub const FULL_PORT_COMPLETE: bool = false;
static WEIGHTED: OnceLock<String> = OnceLock::new();
static PROMOTION: OnceCell<String> = OnceCell::const_new();
pub struct Channel {
    pub destination: Value,
    pub subreddit: String,
    pub ranking: Option<String>,
    pub limit: usize,
    pub requires_submission: bool,
    pub options: Value,
}

pub fn public_modules(app: &App) -> Result<Vec<String>> {
    Ok(queue::schedules(&app.config)?
        .into_iter()
        .map(|(_, m)| m)
        .filter(|m| !m.starts_with("tech_"))
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect())
}
pub async fn identity(app: &App, module: &str) -> Result<(Value, String)> {
    if module == "r_porn" {
        return Ok((json!("@r_porn"), weighted()?));
    }
    if module == "reddit2telegram" {
        return Ok((json!("@reddit2telegram"), String::new()));
    }
    let document = app
        .db
        .collection::<Document>("channels")
        .find_one(doc! {"submodule":module.to_lowercase()})
        .await?;
    let record = if let Some(document) = document {
        model::json_doc(document)?
    } else {
        let local: Value = serde_json::from_str(include_str!("../assets/local_channels.json"))?;
        let local = local[module].clone();
        if local.is_null() {
            return Err(Error::Config);
        }
        json!({"channel":local["t_channel"],"subreddit":local["subreddit"]})
    };
    Ok((
        record["channel"].clone(),
        model::text(&record, "subreddit").into(),
    ))
}
fn weighted() -> Result<String> {
    if let Some(value) = WEIGHTED.get() {
        return Ok(value.clone());
    }
    let data: Value = serde_json::from_str(include_str!("../assets/weighted_channel.json"))?;
    let weights = data["weights"].as_object().ok_or(Error::Config)?;
    let total: u64 = weights.values().filter_map(Value::as_u64).sum();
    let mut draw = rand::thread_rng().gen_range(0..total);
    let mut chosen = None;
    for (name, weight) in weights {
        let weight = weight.as_u64().ok_or(Error::Config)?;
        if draw < weight {
            chosen = Some(name.clone());
            break;
        }
        draw -= weight;
    }
    let value = chosen.ok_or(Error::Config)?;
    let _ = WEIGHTED.set(value);
    Ok(WEIGHTED.get().ok_or(Error::Config)?.clone())
}
pub async fn resolve(app: &App, module: &str) -> Result<Channel> {
    if module == "r_porn" {
        let subreddit = weighted()?;
        let data: Value = serde_json::from_str(include_str!("../assets/weighted_channel.json"))?;
        let mut options = json!({"check_dups":true,"min_upvotes_limit":data["limits"][&subreddit]});
        for kind in ["text", "other", "album", "gif", "img", "video", "gallery"] {
            options[kind] = json!(match kind {
                "text" =>
                    "{title}\n\n{self_text}\n\n{upvotes} upvotes\n/r/{subreddit_name} → #{subreddit_name}\n{short_link}\n{channel}",
                "other" | "album" =>
                    "{title}\n{link}\n\n{upvotes} upvotes\n/r/{subreddit_name} → #{subreddit_name}\n{short_link}\n{channel}",
                _ =>
                    "{title}\n\n{upvotes} upvotes\n/r/{subreddit_name} → #{subreddit_name}\n{short_link}\n{channel}",
            });
        }
        return Ok(Channel {
            destination: json!("@r_porn"),
            subreddit,
            ranking: None,
            limit: 100,
            requires_submission: true,
            options,
        });
    }
    if module == "reddit2telegram" {
        let target = promotion_target(app).await?;
        let (_, subreddit) = identity(app, &target).await?;
        return Ok(Channel {
            destination: json!("@reddit2telegram"),
            subreddit,
            ranking: Some("top".into()),
            limit: 1000,
            requires_submission: true,
            options: json!({}),
        });
    }
    if module.starts_with("tech_") {
        let destination = match module {
            "tech_receiver" => json!("@r_channels"),
            "tech_weekly_radar" => json!("@reddit2telegram"),
            "tech_cleaner" | "tech_anniversary" | "tech_store_stat" => app.config.dev_chat(),
            _ => return Err(Error::Config),
        };
        return Ok(Channel {
            destination,
            subreddit: "all".into(),
            ranking: None,
            limit: 100,
            requires_submission: !matches!(module, "tech_anniversary" | "tech_store_stat"),
            options: json!({}),
        });
    }
    let document = app
        .db
        .collection::<Document>("channels")
        .find_one(doc! {"submodule":module.to_lowercase()})
        .await?;
    let record = if let Some(document) = document {
        model::json_doc(document)?
    } else {
        let local: Value = serde_json::from_str(include_str!("../assets/local_channels.json"))?;
        let local = local[module].clone();
        if local.is_null() {
            return Err(Error::Config);
        }
        json!({"channel":local["t_channel"],"subreddit":local["subreddit"],"submissions_ranking":local["submissions_ranking"],"submissions_limit":local.get("submissions_limit").cloned().unwrap_or(json!(100))})
    };
    let mut options = json!({"min_upvotes_limit":record["min_upvotes_limit"]});
    for kind in ["text", "gif", "video", "img", "album", "gallery", "other"] {
        options[kind] = if record["content"].is_null() {
            json!(true)
        } else {
            record["content"].get(kind).cloned().unwrap_or(json!(false))
        };
    }
    let ranking = record["submissions_ranking"].as_str().map(|s| {
        if ["hot", "new", "top"].contains(&s) {
            s.to_owned()
        } else {
            "hot".into()
        }
    });
    Ok(Channel {
        destination: record["channel"].clone(),
        subreddit: model::text(&record, "subreddit").into(),
        ranking,
        limit: record["submissions_limit"]
            .as_u64()
            .map(|v| v as usize)
            .unwrap_or(usize::MAX),
        requires_submission: true,
        options,
    })
}
pub async fn maintenance(_app: &App, _module: &str, _sender: &Sender) -> Result<Supply> {
    Err(Error::IncompletePort)
}
pub async fn post(
    app: &App,
    module: &str,
    channel: &Channel,
    submission: &Value,
    sender: &Sender,
) -> Result<Supply> {
    match module {
        "reddit2telegram" => promotion(app, submission, sender).await,
        "tech_cleaner" => maintenance::cleaner(app, sender).await,
        "tech_receiver" => maintenance::receiver(app, sender).await,
        "tech_weekly_radar" => maintenance::weekly(app, sender).await,
        "tech_store_stat" | "tech_anniversary" => Err(Error::IncompletePort),
        _ => sender.simple(submission, &channel.options).await,
    }
}
pub async fn tags(app: &App, module: &str) -> Result<Option<String>> {
    if let Some(record) = app
        .db
        .collection::<Document>("channels")
        .find_one(doc! {"submodule":module.to_lowercase()})
        .await?
    {
        if let Ok(tags) = record.get_str("tags") {
            if !tags.is_empty() {
                return Ok(Some(tags.into()));
            }
        }
    }
    match std::fs::read_to_string(
        app.config
            .app
            .join("channels")
            .join(module)
            .join("tags.txt"),
    ) {
        Ok(tags) => Ok(Some(tags)),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(_) => Err(Error::Io),
    }
}
pub async fn nice(
    app: &App,
    module: &str,
    submission: &Value,
    sender: &Sender,
    heading: &str,
    ending: &str,
    channel: Option<&str>,
) -> Result<Supply> {
    let destination = if let Some(channel) = channel {
        channel.to_owned()
    } else {
        identity(app, module)
            .await?
            .0
            .as_str()
            .ok_or(Error::Config)?
            .to_owned()
    };
    let tags = tags(app, module)
        .await?
        .unwrap_or_default()
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ");
    let created = submission["created_utc"].as_f64().ok_or(Error::Config)?;
    let date = Utc
        .timestamp_opt(created as i64, 0)
        .single()
        .ok_or(Error::Config)?
        .format("%Y %b %d")
        .to_string();
    let mut options = json!({"channel_to_promote":destination,"date":date,"tags":tags,"extra_ending":ending,"announcement_heading":heading});
    for kind in ["text", "other", "album", "gif", "img", "video", "gallery"] {
        options[kind] = json!(match kind {
            "text" =>
                "{announcement_heading}{title}\n\n{self_text}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{date}\n{short_link}\nby {channel_to_promote}\n{tags}\n\n{extra_ending}",
            "other" | "album" =>
                "{announcement_heading}{title}\n{link}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{date}\n{short_link}\nby {channel_to_promote}\n{tags}\n\n{extra_ending}",
            _ =>
                "{announcement_heading}{title}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{date}\n{short_link}\nby {channel_to_promote}\n{tags}\n\n{extra_ending}",
        });
    }
    sender.simple(submission, &options).await
}
async fn update_order(app: &App) -> Result<()> {
    let mut order = Document::new();
    for module in public_modules(app)?
        .into_iter()
        .filter(|m| m != "reddit2telegram")
    {
        let (channel, _) = identity(app, &module).await?;
        let channel = channel.as_str().ok_or(Error::Config)?.to_lowercase();
        if let Some(first) = app
            .db
            .collection::<Document>("view_with_first_dates")
            .find_one(doc! {"_id":channel})
            .await?
        {
            if let Some(value) = first.get("first_date") {
                order.insert(module, value.clone());
            }
        }
    }
    app.db.collection::<Document>("settings").update_one(doc!{"setting":"r2t_promotion_queue"},
        doc!{"$setOnInsert":{"already_promoted":[],"counter":0},"$set":{"promotion_order":order}}).upsert(true).await?;
    Ok(())
}
async fn promotion_target(app: &App) -> Result<String> {
    PROMOTION
        .get_or_try_init(|| async {
            let all: Vec<_> = public_modules(app)?
                .into_iter()
                .filter(|m| m != "reddit2telegram")
                .collect();
            if Local::now().weekday().num_days_from_monday() == 6 {
                return all
                    .choose(&mut rand::thread_rng())
                    .cloned()
                    .ok_or(Error::Config);
            }
            let settings = app.db.collection::<Document>("settings");
            if settings
                .find_one(doc! {"setting":"r2t_promotion_queue"})
                .await?
                .is_none()
            {
                update_order(app).await?;
            }
            let record = settings
                .find_one(doc! {"setting":"r2t_promotion_queue"})
                .await?
                .ok_or(Error::Database)?;
            let promoted = record
                .get_array("already_promoted")
                .map_err(|_| Error::Config)?;
            let order = record
                .get_document("promotion_order")
                .map_err(|_| Error::Config)?;
            let mut candidates: Vec<_> = order.iter().collect();
            candidates.sort_by_key(|(_, date)| {
                std::cmp::Reverse(
                    date.as_datetime()
                        .map(|d| d.timestamp_millis())
                        .unwrap_or(0),
                )
            });
            for (name, _) in candidates {
                if all.contains(name) && !promoted.contains(&Bson::String(name.to_owned())) {
                    return Ok(name.to_owned());
                }
            }
            settings
                .update_one(
                    doc! {"setting":"r2t_promotion_queue"},
                    doc! {"$inc":{"counter":1},"$set":{"already_promoted":[]}},
                )
                .await?;
            Err(Error::Config)
        })
        .await
        .cloned()
}
async fn promotion(app: &App, submission: &Value, sender: &Sender) -> Result<Supply> {
    let now = Local::now();
    let weekday = now.weekday().num_days_from_monday();
    if weekday == 5 && [0, 23].contains(&now.hour()) && now.minute() == 1 {
        update_order(app).await?;
        return Ok(Supply::Stop);
    }
    if weekday == 5 {
        return Ok(Supply::Stop);
    }
    let hour = Sha1::digest(now.format("%Y %b %d").to_string())
        .iter()
        .fold(0u32, |n, b| (n * 256 + *b as u32) % 24);
    if now.hour() != hour {
        return Ok(Supply::Stop);
    }
    let target = promotion_target(app).await?;
    let result = nice(app, &target, submission, sender, "", "", None).await?;
    if result == Supply::Sent && weekday < 5 {
        app.db
            .collection::<Document>("settings")
            .update_one(
                doc! {"setting":"r2t_promotion_queue"},
                doc! {"$push":{"already_promoted":target}},
            )
            .await?;
    }
    Ok(result)
}
