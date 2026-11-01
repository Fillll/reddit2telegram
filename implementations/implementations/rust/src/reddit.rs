use crate::{
    http::Http,
    metrics::Metrics,
    model::{Config, Error, Result, now, text},
};
use reqwest::Response;
use serde_json::Value;
use std::{sync::Arc, time::Duration};

pub struct Reddit {
    pub http: Http,
    config: Arc<Config>,
    token: Option<String>,
    expiry: f64,
    next: f64,
}
impl Reddit {
    pub fn new(config: Arc<Config>, metrics: Metrics) -> Result<Self> {
        Ok(Self {
            http: Http::new(metrics, 5)?,
            config,
            token: None,
            expiry: 0.,
            next: 0.,
        })
    }
    async fn authorize(&mut self) -> Result<()> {
        if self.token.is_some() && now() < self.expiry {
            return Ok(());
        }
        let config = &self.config.values["reddit"];
        let response = self
            .http
            .send(
                self.http
                    .client
                    .post("https://www.reddit.com/api/v1/access_token")
                    .header("User-Agent", text(config, "user_agent"))
                    .basic_auth(
                        text(config, "client_id"),
                        Some(text(config, "client_secret")),
                    )
                    .form(&[
                        ("grant_type", "password"),
                        ("username", text(config, "username")),
                        ("password", text(config, "password")),
                    ]),
                20,
                "http",
            )
            .await?;
        if !response.status().is_success() {
            return Err(Error::Reddit);
        }
        let data = self.http.json(response, 20, "http").await?;
        self.token = Some(
            data["access_token"]
                .as_str()
                .ok_or(Error::Reddit)?
                .to_owned(),
        );
        self.expiry = now() + data["expires_in"].as_f64().unwrap_or(3600.) - 10.;
        Ok(())
    }
    fn feedback(&mut self, response: &Response) {
        let value = |key| {
            response
                .headers()
                .get(key)
                .and_then(|h| h.to_str().ok())
                .and_then(|v| v.parse::<f64>().ok())
        };
        if let (Some(remaining), Some(reset), Some(used)) = (
            value("x-ratelimit-remaining"),
            value("x-ratelimit-reset"),
            value("x-ratelimit-used"),
        ) {
            self.next = if remaining <= 0. {
                now() + reset
            } else {
                now()
                    + reset.min((reset - (600. - 600. / (remaining + used) * used)).clamp(0., 10.))
            };
        }
    }
    pub async fn get(&mut self, path: &str, params: &[(String, String)]) -> Result<Value> {
        for attempt in 0..3 {
            if attempt > 0 {
                let base = if attempt == 1 { 0. } else { 2. };
                tokio::time::sleep(Duration::from_secs_f64(base + rand::random::<f64>() * 2.))
                    .await;
            }
            let delay = self.next - now();
            if delay > 0. {
                tokio::time::sleep(Duration::from_secs_f64(delay)).await;
            }
            self.authorize().await?;
            let result = self
                .http
                .send(
                    self.http
                        .client
                        .get(format!("https://oauth.reddit.com{path}"))
                        .header(
                            "User-Agent",
                            text(&self.config.values["reddit"], "user_agent"),
                        )
                        .bearer_auth(self.token.as_deref().ok_or(Error::Reddit)?)
                        .query(params)
                        .query(&[("raw_json", "1")]),
                    20,
                    "http",
                )
                .await;
            match result {
                Ok(response) => {
                    self.feedback(&response);
                    let code = response.status().as_u16();
                    if code == 401 {
                        self.token = None;
                        self.expiry = 0.;
                        if attempt < 2 {
                            continue;
                        }
                    }
                    if [408, 500, 502, 503, 504, 520, 522].contains(&code) && attempt < 2 {
                        continue;
                    }
                    if code >= 400 {
                        return Err(Error::Reddit);
                    }
                    return self.http.json(response, 20, "http").await;
                }
                Err(error) => {
                    if attempt == 2 {
                        return Err(error);
                    }
                }
            }
        }
        Err(Error::Reddit)
    }
    pub async fn listing(
        &mut self,
        subreddit: &str,
        ranking: &str,
        limit: usize,
        after: Option<&str>,
    ) -> Result<Value> {
        let mut params = vec![("limit".into(), limit.min(25).to_string())];
        if let Some(after) = after {
            params.push(("after".into(), after.into()));
        }
        if ranking == "top" {
            params.push(("t".into(), "all".into()));
        }
        self.get(&format!("/r/{subreddit}/{ranking}"), &params)
            .await
    }
    pub async fn hydrate(&mut self, submission: &Value) -> Result<Value> {
        let id = submission["id"]
            .as_str()
            .filter(|s| !s.is_empty())
            .ok_or(Error::Reddit)?;
        let response = self
            .get(
                &format!("/comments/{id}"),
                &[
                    ("limit".into(), "2048".into()),
                    ("sort".into(), "confidence".into()),
                ],
            )
            .await?;
        let data = &response[0]["data"]["children"][0]["data"];
        if !data.is_object() {
            return Err(Error::Reddit);
        }
        Ok(data.clone())
    }
}
