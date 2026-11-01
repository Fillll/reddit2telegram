use crate::{
    metrics::Metrics,
    model::{Error, Result},
};
use bytes::Bytes;
use futures_util::{StreamExt, stream};
use reqwest::{Client, Method, Response, StatusCode};
use serde_json::Value;
use std::{path::Path, sync::Arc, time::Duration};
use tokio::io::AsyncWriteExt;
use tokio_util::io::ReaderStream;

#[derive(Clone)]
pub struct Http {
    pub client: Client,
    pub metrics: Metrics,
    head: Arc<tokio::sync::OnceCell<Client>>,
}
impl Http {
    pub fn new(metrics: Metrics, connect: u64) -> Result<Self> {
        let client = Self::build_client(
            metrics.clone(),
            connect,
            if connect == 30 { 30 } else { 20 },
            connect == 30,
        )?;
        Ok(Self {
            client,
            metrics,
            head: Arc::new(tokio::sync::OnceCell::new()),
        })
    }
    fn build_client(metrics: Metrics, connect: u64, read: u64, telegram: bool) -> Result<Client> {
        let redirects = if telegram {
            reqwest::redirect::Policy::none()
        } else {
            reqwest::redirect::Policy::custom(move |attempt| {
                if attempt.previous().len() >= 30 {
                    return attempt.error("redirect limit");
                }
                metrics.status("http", attempt.status().as_u16());
                metrics.count("http_request_attempts", 1);
                attempt.follow()
            })
        };
        let client = Client::builder()
            .http1_only()
            .connect_timeout(Duration::from_secs(connect))
            .read_timeout(Duration::from_secs(read))
            .pool_max_idle_per_host(1)
            .redirect(redirects)
            .build()
            .map_err(|_| Error::Network)?;
        Ok(client)
    }
    pub async fn send(
        &self,
        builder: reqwest::RequestBuilder,
        _timeout: u64,
        prefix: &str,
    ) -> Result<Response> {
        self.metrics.count(&format!("{prefix}_request_attempts"), 1);
        let response = match builder.send().await {
            Ok(response) => response,
            Err(error) => {
                self.metrics.count(&format!("{prefix}_transport_errors"), 1);
                return Err(if error.is_timeout() {
                    Error::Timeout
                } else {
                    Error::Network
                });
            }
        };
        self.metrics.status(prefix, response.status().as_u16());
        Ok(response)
    }
    pub async fn request(&self, method: Method, url: &str, timeout: u64) -> Result<Response> {
        let client = if method == Method::HEAD {
            self.head
                .get_or_try_init(|| async { Self::build_client(self.metrics.clone(), 3, 8, false) })
                .await?
        } else {
            &self.client
        };
        self.send(client.request(method, url), timeout, "http")
            .await
    }
    pub async fn body(
        &self,
        mut response: Response,
        timeout: u64,
        max: usize,
        prefix: &str,
    ) -> Result<Vec<u8>> {
        let mut body = Vec::new();
        loop {
            let chunk = tokio::time::timeout(Duration::from_secs(timeout), response.chunk())
                .await
                .map_err(|_| Error::Timeout)?
                .map_err(|_| Error::Network)?;
            let Some(chunk) = chunk else {
                break;
            };
            self.metrics
                .count(&format!("{prefix}_response_body_bytes"), chunk.len() as u64);
            if body.len() + chunk.len() > max {
                return Err(Error::Media);
            }
            body.extend_from_slice(&chunk);
        }
        Ok(body)
    }
    pub async fn json(&self, response: Response, timeout: u64, prefix: &str) -> Result<Value> {
        serde_json::from_slice(&self.body(response, timeout, usize::MAX, prefix).await?)
            .map_err(|_| Error::Network)
    }
    pub async fn metadata(&self, url: &str) -> Result<String> {
        let response = self.request(Method::GET, url, 20).await?;
        if !response.status().is_success() {
            return Err(Error::Media);
        }
        Ok(
            String::from_utf8_lossy(&self.body(response, 20, 1024 * 1024, "http").await?)
                .into_owned(),
        )
    }
    pub async fn download(&self, url: &str, path: &Path, limit: u64) -> Result<bool> {
        let result: Result<bool> = async {
            let mut response = self.request(Method::GET, url, 20).await?;
            if !response.status().is_success()
                || response.content_length().is_some_and(|n| n > limit)
            {
                return Ok(false);
            }
            let mut file = tokio::fs::File::create(path).await?;
            let mut size = 0;
            loop {
                let chunk = tokio::time::timeout(Duration::from_secs(20), response.chunk())
                    .await
                    .map_err(|_| Error::Timeout)?
                    .map_err(|_| Error::Network)?;
                let Some(chunk) = chunk else {
                    break;
                };
                self.metrics
                    .count("http_response_body_bytes", chunk.len() as u64);
                size += chunk.len() as u64;
                if size > limit {
                    return Ok(false);
                }
                file.write_all(&chunk).await?;
            }
            file.flush().await?;
            Ok(true)
        }
        .await;
        if !matches!(result, Ok(true)) {
            let _ = tokio::fs::remove_file(path).await;
        }
        Ok(result.unwrap_or(false))
    }
    pub async fn telegram(&self, token: &str, method: &str, params: Value) -> Result<Value> {
        let bytes = serde_json::to_vec(&params)?;
        let metrics = self.metrics.clone();
        let body = reqwest::Body::wrap_stream(stream::once(async move {
            metrics.count("telegram_request_body_bytes", bytes.len() as u64);
            Ok::<_, std::io::Error>(Bytes::from(bytes))
        }));
        let response = self
            .send(
                self.client
                    .post(format!("https://api.telegram.org/bot{token}/{method}"))
                    .header("Content-Type", "application/json")
                    .body(body),
                30,
                "telegram",
            )
            .await?;
        self.telegram_result(response, method).await
    }
    pub async fn telegram_video(&self, token: &str, params: &Value, path: &Path) -> Result<Value> {
        let boundary = format!("r2t{}", uuid::Uuid::new_v4().simple());
        let mut prefix = Vec::new();
        for (key, value) in params.as_object().ok_or(Error::Config)? {
            let value = if let Some(v) = value.as_str() {
                v.to_owned()
            } else {
                value.to_string()
            };
            prefix.extend_from_slice(format!("--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{value}\r\n").as_bytes());
        }
        prefix.extend_from_slice(format!("--{boundary}\r\nContent-Disposition: form-data; name=\"video\"; filename=\"video.mp4\"\r\nContent-Type: video/mp4\r\n\r\n").as_bytes());
        let tail = Bytes::from(format!("\r\n--{boundary}--\r\n"));
        let file = tokio::fs::File::open(path).await?;
        let length = file.metadata().await?.len() + prefix.len() as u64 + tail.len() as u64;
        let chunks = stream::once(async move { Ok::<Bytes, std::io::Error>(Bytes::from(prefix)) })
            .chain(ReaderStream::with_capacity(file, 256 * 1024))
            .chain(stream::once(
                async move { Ok::<Bytes, std::io::Error>(tail) },
            ));
        let metrics = self.metrics.clone();
        let chunks = chunks.map(move |chunk| {
            if let Ok(ref data) = chunk {
                metrics.count("telegram_request_body_bytes", data.len() as u64);
            }
            chunk
        });
        let response = self
            .send(
                self.client
                    .post(format!("https://api.telegram.org/bot{token}/sendVideo"))
                    .header(
                        "Content-Type",
                        format!("multipart/form-data; boundary={boundary}"),
                    )
                    .header("Content-Length", length)
                    .body(reqwest::Body::wrap_stream(chunks)),
                30,
                "telegram",
            )
            .await?;
        self.telegram_result(response, "sendVideo").await
    }
    async fn telegram_result(&self, response: Response, method: &str) -> Result<Value> {
        let status = response.status();
        let body = self.json(response, 30, "telegram").await?;
        if !status.is_success() || body["ok"] != true {
            return Err(if status == StatusCode::BAD_REQUEST {
                Error::Rejected
            } else {
                Error::Telegram
            });
        }
        let result = body["result"].clone();
        if method.starts_with("send") || method == "forwardMessage" {
            self.metrics.delivery(&result);
        }
        Ok(result)
    }
}
