//! Channel policy port. Deployment stays disabled until every scheduled custom
//! channel, maintenance job and durable announcement state machine is complete.
use crate::{
    model::{self, Error, Result, Supply},
    queue::App,
    sender::Sender,
};
use mongodb::bson::{Document, doc};
use serde_json::{Value, json};

pub const FULL_PORT_COMPLETE: bool = false;
pub struct Channel {
    pub destination: Value,
    pub subreddit: String,
    pub ranking: Option<String>,
    pub limit: usize,
    pub requires_submission: bool,
    pub options: Value,
}
pub async fn resolve(app: &App, module: &str) -> Result<Channel> {
    if matches!(
        module,
        "r_porn"
            | "reddit2telegram"
            | "tech_cleaner"
            | "tech_receiver"
            | "tech_weekly_radar"
            | "tech_store_stat"
            | "tech_anniversary"
    ) {
        return Err(Error::IncompletePort);
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
    _app: &App,
    module: &str,
    channel: &Channel,
    submission: &Value,
    sender: &Sender,
) -> Result<Supply> {
    if matches!(
        module,
        "r_porn"
            | "reddit2telegram"
            | "tech_cleaner"
            | "tech_receiver"
            | "tech_weekly_radar"
            | "tech_store_stat"
            | "tech_anniversary"
    ) {
        return Err(Error::IncompletePort);
    }
    sender.simple(submission, &channel.options).await
}
