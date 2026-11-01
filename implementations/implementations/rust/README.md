# Rust implementation

This native port uses MongoDB's Rust driver, Tokio, reqwest/rustls, the existing
MongoDB task and posting schema, and the same ffmpeg command as Python. No
Python subprocess executes application work. Configuration remains the existing
`reddit2telegram/configs/prod.yml`; run from `reddit2telegram/`.

The complete scheduled workload is implemented, including subscriber sweeps,
achievement and anniversary delivery, compatible leases/checkpoints, Sentry and
developer reporting. See [PORTING.md](PORTING.md) for the source coverage review.
Compilation and source review do not establish live correctness or performance;
those observations come from the single scheduled 24-hour live window.

Keep this branch unmerged while a Python measurement is active. The binary may
take production traffic only after its final checked artifact is selected by the
benchmark runner and the preceding configuration has finished its window.

```sh
cargo build --release --locked --manifest-path implementations/implementations/rust/Cargo.toml
implementations/implementations/rust/target/release/r2t-rust --describe
```

Release compilation takes place on GitHub Actions so compiler load does not
contend with the active live measurement on the production host. Compilation
does not send benchmark traffic. Only the single authorized 24-hour live run
will provide performance observations.

`assets/` contains literal channel configuration extracted from existing Python
source, including the weighted channel's weights and score thresholds. The
production binary reads these as data; it does not interpret Python source.
Database-backed channel settings are looked up from the real MongoDB database.

The binary emits schema-1 benchmark events compatible with the external runner,
including job timing, acknowledged messages, media mix, HTTP body bytes,
rate-limit/error counts, and hashes of posting records. Logs never include
request URLs, bot tokens, message bodies, or transport error strings.
