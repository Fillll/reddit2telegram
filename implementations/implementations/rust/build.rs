use std::process::Command;
fn main() {
    println!("cargo:rerun-if-changed=../../../VERSION");
    let rustc = std::env::var("RUSTC").unwrap_or_else(|_| "rustc".into());
    if let Ok(result) = Command::new(rustc).arg("--version").output() {
        println!(
            "cargo:rustc-env=R2T_RUSTC_VERSION={}",
            String::from_utf8_lossy(&result.stdout).trim()
        );
    }
    if let Ok(result) = Command::new("git").args(["rev-parse", "HEAD"]).output() {
        println!(
            "cargo:rustc-env=R2T_BUILD_COMMIT={}",
            String::from_utf8_lossy(&result.stdout).trim()
        );
    }
}
