use mongodb::{
    Database,
    bson::{self, Bson, Document},
};
use serde_json::Value;
use std::{
    fmt,
    path::{Path, PathBuf},
    time::{Duration, SystemTime, UNIX_EPOCH},
};

pub type Result<T> = std::result::Result<T, Error>;

// Transport error displays often contain request URLs, including Telegram tokens.
// Retain only a safe category in native logs, events, and operational reports.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Error {
    Config,
    Io,
    Database,
    Network,
    Timeout,
    Reddit,
    Telegram,
    Rejected,
    Media,
    Template,
    UnknownTask,
    IncompletePort,
}
impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{self:?}")
    }
}
impl std::error::Error for Error {}
impl From<std::io::Error> for Error {
    fn from(_: std::io::Error) -> Self {
        Self::Io
    }
}
impl From<mongodb::error::Error> for Error {
    fn from(_: mongodb::error::Error) -> Self {
        Self::Database
    }
}
impl From<serde_json::Error> for Error {
    fn from(_: serde_json::Error) -> Self {
        Self::Config
    }
}
impl From<url::ParseError> for Error {
    fn from(_: url::ParseError) -> Self {
        Self::Media
    }
}

pub fn now() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs_f64()
}
pub fn date() -> bson::DateTime {
    bson::DateTime::from_millis((now() * 1000.) as i64)
}
pub fn text<'a>(v: &'a Value, key: &str) -> &'a str {
    v.get(key).and_then(Value::as_str).unwrap_or("")
}
pub fn number(v: &Value, key: &str, default: i64) -> i64 {
    v.get(key).and_then(Value::as_i64).unwrap_or(default)
}
pub fn truth(v: &Value) -> bool {
    match v {
        Value::Null => false,
        Value::Bool(b) => *b,
        Value::String(s) => !s.is_empty(),
        Value::Number(n) => n.as_f64().unwrap_or(0.) != 0.,
        Value::Array(a) => !a.is_empty(),
        Value::Object(o) => !o.is_empty(),
    }
}
pub fn numeric(doc: &Document, key: &str) -> Option<f64> {
    match doc.get(key)? {
        Bson::Double(v) => Some(*v),
        Bson::Int32(v) => Some(*v as f64),
        Bson::Int64(v) => Some(*v as f64),
        _ => None,
    }
}
pub fn json_doc(doc: Document) -> Result<Value> {
    bson::from_document(doc).map_err(|_| Error::Config)
}

pub async fn short_sleep(coef: f64) {
    pause(2. * coef, 4. * coef).await;
}
pub async fn long_sleep(coef: f64) {
    pause(8. * coef, 20. * coef).await;
}
async fn pause(low: f64, high: f64) {
    use rand::Rng;
    let secs = rand::thread_rng().gen_range(low..high);
    tokio::time::sleep(Duration::from_secs_f64(secs)).await;
}

#[derive(Clone)]
pub struct Config {
    pub values: Value,
    pub path: PathBuf,
    pub app: PathBuf,
    pub root: PathBuf,
}
impl Config {
    pub fn load(path: &Path) -> Result<Self> {
        let path = path.canonicalize()?;
        let values: Value =
            serde_yaml::from_slice(&std::fs::read(&path)?).map_err(|_| Error::Config)?;
        let app = path
            .parent()
            .and_then(Path::parent)
            .ok_or(Error::Config)?
            .to_path_buf();
        let root = app.parent().ok_or(Error::Config)?.to_path_buf();
        Ok(Self {
            values,
            path,
            app,
            root,
        })
    }
    pub fn worker_size(&self) -> usize {
        self.values["pool"]["size"].as_u64().unwrap_or_else(|| {
            std::thread::available_parallelism()
                .map(|n| n.get() as u64)
                .unwrap_or(1)
        }) as usize
    }
    pub fn max_pending(&self) -> usize {
        self.values["consumer"]["max_pending"]
            .as_u64()
            .unwrap_or(self.worker_size() as u64) as usize
    }
    pub fn batch_size(&self) -> usize {
        self.values["consumer"]["batch_size"]
            .as_u64()
            .unwrap_or(self.worker_size() as u64 * 2) as usize
    }
    pub fn cron_path(&self) -> PathBuf {
        let p = PathBuf::from(text(&self.values, "cron_file"));
        if p.is_absolute() { p } else { self.app.join(p) }
    }
    pub fn dev_chat(&self) -> Value {
        self.values["telegram"]["dev_chat"].clone()
    }
    pub async fn database(&self) -> Result<Database> {
        let host = text(&self.values["db"], "host");
        let uri = if host.contains("://") {
            host.to_owned()
        } else {
            format!("mongodb://{host}")
        };
        let client = mongodb::Client::with_uri_str(uri).await?;
        Ok(client.database(text(&self.values["db"], "name")))
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Supply {
    Sent,
    Reject,
    Skip,
    Stop,
}

pub fn format(
    template: &str,
    fields: &std::collections::HashMap<String, String>,
) -> Result<String> {
    let mut result = String::new();
    let mut chars = template.chars().peekable();
    while let Some(ch) = chars.next() {
        match ch {
            '{' if chars.peek() == Some(&'{') => {
                chars.next();
                result.push('{');
            }
            '}' if chars.peek() == Some(&'}') => {
                chars.next();
                result.push('}');
            }
            '{' => {
                let mut name = String::new();
                let mut closed = false;
                for c in chars.by_ref() {
                    if c == '}' {
                        closed = true;
                        break;
                    }
                    name.push(c);
                }
                if !closed {
                    return Err(Error::Template);
                }
                result.push_str(fields.get(&name).ok_or(Error::Template)?);
            }
            '}' => return Err(Error::Template),
            _ => result.push(ch),
        }
    }
    Ok(result)
}

pub fn human(score: i64) -> String {
    if score.abs() < 1000 {
        return score.to_string();
    }
    let mut value = score as f64;
    let mut magnitude = 0;
    while value.abs() >= 1000. && magnitude < 5 {
        magnitude += 1;
        value = (value / 100.).round_ties_even() / 10.;
    }
    format!("{value:.1}{}", ["", "k", "M", "G", "T", "P"][magnitude])
}
