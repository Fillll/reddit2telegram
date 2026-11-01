use crate::model::{Error, now};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    fs::OpenOptions,
    io::Write,
    path::Path,
    sync::{Arc, Mutex},
    time::Instant,
};

#[derive(Clone, Default)]
pub struct Metrics {
    state: Option<Arc<Mutex<State>>>,
}
struct State {
    run: Value,
    task_id: String,
    module: String,
    wait: Option<f64>,
    started: Instant,
    counters: BTreeMap<String, u64>,
}

pub fn active(root: &Path) -> Option<Value> {
    let run: Value = serde_json::from_slice(
        &std::fs::read(root.join("implementations/benchmarks/state/active.json")).ok()?,
    )
    .ok()?;
    (run["started_at"].as_f64()? <= now() && now() < run["deadline"].as_f64()?).then_some(run)
}
pub fn emit(run: &Value, event: &str, mut fields: Value) {
    if now() < run["started_at"].as_f64().unwrap_or(f64::INFINITY)
        || now() >= run["deadline"].as_f64().unwrap_or(0.)
    {
        return;
    }
    fields["schema"] = json!(1);
    fields["run_id"] = run["run_id"].clone();
    fields["ts"] = json!(now());
    fields["event"] = json!(event);
    if let Some(path) = run["events_path"].as_str() {
        let mut options = OpenOptions::new();
        options.create(true).append(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            options.mode(0o600);
        }
        if let Ok(mut file) = options.open(path) {
            if let Ok(mut line) = serde_json::to_vec(&fields) {
                line.push(b'\n');
                if file.write_all(&line).is_err() {
                    eprintln!("benchmark event write failed");
                }
            }
        }
    }
}
impl Metrics {
    pub fn begin(root: &Path, task_id: &str, module: &str, created: Option<f64>) -> Self {
        let Some(run) = active(root) else {
            return Self::default();
        };
        let wait = created.map(|t| (now() - t).max(0.));
        emit(
            &run,
            "job_start",
            json!({"task_id":task_id,"module":module,"queue_wait_seconds":wait}),
        );
        Self {
            state: Some(Arc::new(Mutex::new(State {
                run,
                task_id: task_id.into(),
                module: module.into(),
                wait,
                started: Instant::now(),
                counters: BTreeMap::new(),
            }))),
        }
    }
    pub fn count(&self, key: &str, n: u64) {
        if let Some(state) = &self.state {
            if let Ok(mut state) = state.lock() {
                *state.counters.entry(key.into()).or_default() += n;
            }
        }
    }
    pub fn status(&self, prefix: &str, status: u16) {
        self.count(&format!("{prefix}_requests"), 1);
        if status == 429 {
            self.count(&format!("{prefix}_rate_limits"), 1);
        }
        if status >= 400 {
            self.count(&format!("{prefix}_http_errors"), 1);
        }
    }
    pub fn finish(&self, outcome: std::result::Result<(), Error>) {
        if let Some(state) = &self.state {
            if let Ok(state) = state.lock() {
                emit(
                    &state.run,
                    "job_end",
                    json!({"task_id":state.task_id,"module":state.module,"status":if outcome.is_ok(){"success"}else{"failed"},"error_type":outcome.err().map(|e|e.to_string()),"duration_seconds":state.started.elapsed().as_secs_f64(),"queue_wait_seconds":state.wait,"counters":state.counters}),
                );
            }
        }
    }
    pub fn post(&self, channel: &str, url: &str, sent: bool) {
        self.count(
            if sent {
                "posts_recorded_sent"
            } else {
                "candidates_rejected"
            },
            1,
        );
        if !sent {
            return;
        }
        if let Some(state) = &self.state {
            if let Ok(state) = state.lock() {
                let hash = format!(
                    "{:x}",
                    Sha256::digest(format!(
                        "{}\0{}",
                        channel.to_lowercase(),
                        url.to_lowercase()
                    ))
                );
                emit(
                    &state.run,
                    "post_record",
                    json!({"task_id":state.task_id,"post_key":hash}),
                );
            }
        }
    }
    pub fn delivery(&self, result: &Value) {
        let messages = match result {
            Value::Array(a) => a.clone(),
            _ => vec![result.clone()],
        };
        for m in messages {
            if m.get("message_id").is_none() {
                continue;
            }
            self.count("telegram_messages", 1);
            let kind = if m.get("video").is_some() {
                "video"
            } else if m.get("animation").is_some() {
                "animation"
            } else if m.get("photo").is_some() {
                "photo"
            } else if m.get("document").is_some() {
                "document"
            } else if m.get("audio").is_some() {
                "audio"
            } else {
                "text_or_other"
            };
            self.count(&format!("telegram_messages_{kind}"), 1);
        }
    }
}
