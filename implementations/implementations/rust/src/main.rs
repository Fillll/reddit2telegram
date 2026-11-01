mod custom;
mod http;
mod maintenance;
mod metrics;
mod model;
mod queue;
mod reddit;
mod sender;

use model::{Error, Result};
use std::path::PathBuf;

#[tokio::main]
async fn main() {
    if let Err(error) = run().await {
        eprintln!("r2t-rust: {error}");
        std::process::exit(1);
    }
}
async fn run() -> Result<()> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    if args.iter().any(|a| a == "--version") {
        println!("r2t-rust {}", include_str!("../../../../VERSION").trim());
        return Ok(());
    }
    if args.iter().any(|a| a == "--describe") {
        println!(
            "{}",
            serde_json::json!({"language":"rust","version":include_str!("../../../../VERSION").trim(),"compiler":option_env!("R2T_RUSTC_VERSION"),"source_commit":option_env!("R2T_BUILD_COMMIT"),"full_port_complete":custom::FULL_PORT_COMPLETE,"architecture":"MongoDB queue, bounded async workers, two-video semaphore","profile":if cfg!(debug_assertions){"debug"}else{"release"},"optimization":"release; thin LTO; one codegen unit"})
        );
        return Ok(());
    }
    // A partial port must never take production traffic or enter the benchmark.
    if !custom::FULL_PORT_COMPLETE {
        return Err(Error::IncompletePort);
    }
    let role = args.first().map(String::as_str).unwrap_or("consumer");
    let path = args
        .windows(2)
        .find(|pair| pair[0] == "--config")
        .map(|pair| PathBuf::from(&pair[1]))
        .unwrap_or_else(|| PathBuf::from("configs/prod.yml"));
    let app = queue::App::load(&path).await?;
    match role {
        "consumer" => queue::consumer(app).await,
        "scheduler" => queue::scheduler(app).await,
        _ => Err(Error::Config),
    }
}
