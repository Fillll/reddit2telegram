//! Existing Sentry and developer-chat reporting, without credential-bearing errors.
use crate::{
    metrics::Metrics,
    model::{Config, Error, Result, date, numeric},
    queue::App,
};
use chrono::Local;
use mongodb::{
    bson::{Document, doc},
    options::ReturnDocument,
};
use std::{sync::Arc, time::Duration};

#[derive(Default)]
pub struct Context {
    pub channel: Option<String>,
    pub link: Option<String>,
}
#[derive(Clone)]
pub struct Reporter {
    inner: Arc<Inner>,
}
struct Inner {
    client: Option<sentry::Client>,
}
impl Drop for Inner {
    fn drop(&mut self) {
        if let Some(client) = &self.client {
            client.close(Some(Duration::from_secs(2)));
        }
    }
}
impl Reporter {
    pub fn new(config: &Config) -> Result<Self> {
        let _ = rustls::crypto::ring::default_provider().install_default();
        let client = if let Some(dsn) = config.values["sentry"]
            .as_str()
            .filter(|dsn| !dsn.is_empty())
        {
            let dsn = dsn.parse().map_err(|_| Error::Config)?;
            let options = sentry::ClientOptions {
                dsn: Some(dsn),
                transport: Some(Arc::new(sentry::transports::DefaultTransportFactory)),
                release: Some(include_str!("../../../../VERSION").trim().into()),
                debug: false,
                send_default_pii: false,
                ..Default::default()
            };
            Some(sentry::Client::from_config(options))
        } else {
            None
        };
        Ok(Self {
            inner: Arc::new(Inner { client }),
        })
    }
    pub fn capture(&self, error: Error, module: &str) {
        if let Some(client) = &self.inner.client {
            let mut event = sentry::event_from_error(&error);
            event.logger = Some("r2t-rust".into());
            event
                .extra
                .insert("submodule".into(), serde_json::json!(module));
            client.capture_event(event, None);
        }
    }
}
pub async fn developer(
    app: &App,
    module: &str,
    context: &Context,
    error: Error,
    metrics: Metrics,
) -> Result<()> {
    let sender = app.sender(app.config.dev_chat(), metrics).await?;
    let channel = context.channel.clone().unwrap_or_else(|| sender.channel());
    let errors = app.db.collection::<Document>("errors");
    let (filter, link_title) = if let Some(link) = &context.link {
        (
            doc! {"channel":channel.to_lowercase(),"url":link.to_lowercase()},
            format!("link: {link}\n"),
        )
    } else {
        (
            doc! {"channel":channel.to_lowercase(),"link":"_NO_","date":Local::now().format("%Y-%m-%d").to_string()},
            String::new(),
        )
    };
    let count = errors
        .find_one_and_update(filter, doc! {"$inc":{"cnt":1},"$set":{"ts":date()}})
        .projection(doc! {"cnt":1,"_id":0})
        .return_document(ReturnDocument::After)
        .upsert(true)
        .await?
        .ok_or(Error::Database)?;
    let count = numeric(&count, "cnt").ok_or(Error::Database)? as i64;
    let title = format!("submodule: {module}\nchannel: {channel}\n{link_title}error_cnt: {count}");
    sender
        .send_text(
            &format!("<b>r2t error</b>\n{title}\n\n\n<pre>{error}</pre>"),
            false,
            Some("HTML"),
        )
        .await?;
    Ok(())
}
