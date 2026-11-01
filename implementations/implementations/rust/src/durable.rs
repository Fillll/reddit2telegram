//! MongoDB leases and per-message checkpoints compatible with Python records.
use crate::{
    model::{Error, Result, date},
    sender::AckSink,
};
use async_trait::async_trait;
use mongodb::{
    Collection,
    bson::{self, Bson, Document, doc},
    options::ReturnDocument,
};
use std::sync::{Arc, Mutex};

pub fn oldest_date() -> bson::DateTime {
    bson::DateTime::from_millis(-62_135_596_800_000)
}
pub fn integer(value: &Bson) -> Option<i64> {
    match value {
        Bson::Int32(n) => Some(*n as i64),
        Bson::Int64(n) => Some(*n),
        Bson::Double(n) if n.is_finite() => Some(*n as i64),
        _ => None,
    }
}
pub fn identifiers(event: &Document, key: &str) -> Vec<i64> {
    event
        .get_array(key)
        .map(|a| a.iter().filter_map(integer).collect())
        .unwrap_or_default()
}
pub fn duplicate_key(error: &mongodb::error::Error) -> bool {
    use mongodb::error::{ErrorKind, WriteFailure};
    match error.kind.as_ref() {
        ErrorKind::Write(WriteFailure::WriteError(error)) => error.code == 11000,
        ErrorKind::Command(error) => error.code == 11000,
        _ => false,
    }
}

pub struct Lease {
    pub settings: Collection<Document>,
    pub key: String,
    pub owner: String,
    pub previous_owner: Option<String>,
}
impl Lease {
    pub fn new(settings: Collection<Document>, key: &str) -> Self {
        Self {
            settings,
            key: key.into(),
            owner: uuid::Uuid::new_v4().simple().to_string(),
            previous_owner: None,
        }
    }
    pub async fn acquire(&mut self) -> Result<bool> {
        let created = self
            .settings
            .update_one(
                doc! {"_id":&self.key},
                doc! {"$setOnInsert":{"setting":&self.key,"expires_at":oldest_date()}},
            )
            .upsert(true)
            .await;
        if let Err(error) = created {
            if !duplicate_key(&error) {
                return Err(Error::Database);
            }
        }
        let now = date();
        let expiry = bson::DateTime::from_millis(now.timestamp_millis() + 7_200_000);
        let previous = self
            .settings
            .find_one_and_update(
                doc! {"_id":&self.key,"expires_at":{"$lte":now}},
                doc! {"$set":{"owner":&self.owner,"expires_at":expiry}},
            )
            .return_document(ReturnDocument::Before)
            .await?;
        self.previous_owner = previous
            .as_ref()
            .and_then(|d| d.get_str("owner").ok())
            .map(str::to_owned);
        Ok(previous.is_some())
    }
    pub async fn renew(&self) -> Result<()> {
        let now = date();
        let expiry = bson::DateTime::from_millis(now.timestamp_millis() + 7_200_000);
        let result = self
            .settings
            .update_one(
                doc! {"_id":&self.key,"owner":&self.owner,"expires_at":{"$gt":now}},
                doc! {"$set":{"expires_at":expiry}},
            )
            .await?;
        if result.matched_count == 0 {
            return Err(Error::Lease);
        }
        Ok(())
    }
    pub async fn release(&self) -> Result<()> {
        self.settings
            .update_one(
                doc! {"_id":&self.key,"owner":&self.owner},
                doc! {"$set":{"expires_at":oldest_date()}},
            )
            .await?;
        Ok(())
    }
}

pub enum AckMode {
    Achievement,
    Anniversary { path: String },
}
pub struct Checkpoint {
    settings: Collection<Document>,
    selector: Document,
    mode: AckMode,
    ids: Mutex<Vec<i64>>,
}
impl Checkpoint {
    pub fn new(
        settings: Collection<Document>,
        selector: Document,
        mode: AckMode,
        ids: Vec<i64>,
    ) -> Arc<Self> {
        Arc::new(Self {
            settings,
            selector,
            mode,
            ids: Mutex::new(ids),
        })
    }
    pub fn ids(&self) -> Result<Vec<i64>> {
        self.ids
            .lock()
            .map(|ids| ids.clone())
            .map_err(|_| Error::Announcement)
    }
}
#[async_trait]
impl AckSink for Checkpoint {
    async fn record(&self, new: Vec<i64>) -> Result<()> {
        let ids = {
            let mut ids = self.ids.lock().map_err(|_| Error::Announcement)?;
            ids.extend(new.iter().copied());
            ids.clone()
        };
        let update = match &self.mode {
            AckMode::Achievement => doc! {"$addToSet":{"message_ids":{"$each":new}}},
            AckMode::Anniversary { path } => {
                let mut values = Document::new();
                values.insert(format!("{path}.state"), "sent");
                values.insert(format!("{path}.message_ids"), ids);
                values.insert(format!("{path}.sent_at"), date());
                doc! {"$set":values}
            }
        };
        let result = self
            .settings
            .update_one(self.selector.clone(), update)
            .await?;
        if matches!(self.mode, AckMode::Anniversary { .. }) && result.matched_count == 0 {
            return Err(Error::Lease);
        }
        Ok(())
    }
}
