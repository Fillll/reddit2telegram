# Rust source coverage review

The reference is the deployed Python 3.12 source at `64bd864`, including the
preserved local supplier/retry/error-policy patches recorded by the fresh run's
source and dirty-diff hashes. This review maps application behavior to native
code. It is not a replay, synthetic test, or live performance result.

## Scheduled workload

| Python behavior | Native implementation |
| --- | --- |
| Cron TSV, existing masks, randomized submission, config filename hydration | `queue.rs` |
| MongoDB task values 1–5, 25-minute expiry, startup recovery, bounded pending work, five-second polling | `queue.rs` |
| Batch claims before submission; draining after signals or consumer failures | `queue.rs` |
| Password OAuth, feedback-based pacing, three transport attempts, ten consecutive listing retries | `reddit.rs`, `queue.rs` |
| Bounded 25-candidate pages and configured total limits, including legacy unlimited listings | `reddit.rs`, `custom.rs` |
| Cached media fields and authenticated hydration when required fields are absent | `reddit.rs`, `sender.rs` |
| Text, photo, animation, video, gallery, Imgur albums, links and crossposts | `sender.rs` |
| Caption/text splitting, Markdown rejection fallback, original content rules | `sender.rs`, `model.rs` |
| 50 MiB limits, two video pipelines, streaming files, ffmpeg stream-copy command and cleanup | `sender.rs` |
| Posting history, error thresholds and media hashes | `sender.rs`, `reporting.rs` |
| DB channel rules and literal local defaults | `custom.rs`, `assets/local_channels.json` |
| `r_porn` weighted source, score thresholds and formatting | `custom.rs`, `assets/weighted_channel.json` |
| `reddit2telegram` promotion queue, selected source and scheduled formatting | `custom.rs` |
| `tech_receiver` update cursor, owner restriction, forwarding, persisted conversation and DB upserts | `maintenance.rs` |
| `tech_cleaner` existing cleanup and task-statistics accounting | `maintenance.rs` |
| `tech_weekly_radar` active channels, subscriber growth and paginated directory | `maintenance.rs` |
| `tech_store_stat` subscriber/admin sweep, milestone crossings and reports | `achievements.rs` |
| `tech_anniversary` stable dates, yearly uniqueness and frozen directory messages | `anniversaries.rs` |
| Two-hour leases, per-message acknowledgments, forwarding checkpoints and ambiguous-send holds | `durable.rs`, `achievements.rs`, `anniversaries.rs` |
| Existing Sentry destination and developer error reporting | `reporting.rs` |
| Operational logging and allocator maintenance | `model.rs`, `queue.rs`, `sender.rs` |
| Schema-1 job timing, delivery mix, HTTP body counts and duplicate-record hashes | `metrics.rs`, `http.rs` |

The scheduler reads the entire live schedule. Normal jobs resolve channel data
from the live MongoDB database. Literal source metadata is configuration data;
no Python process executes native application work. The current configured DB
templates use only the supported `{title}` field; source-defined promotion and
weighted-channel templates use the additional implemented named fields.

## Persisted delivery compatibility

Achievement events retain the `r2t_achievement_delivery` kind, unique IDs,
message IDs, forwarding IDs, attempts and completion fields. Existing
`r2t_achievements` history prevents repeated milestones. Each acknowledged part
is persisted before proceeding. Reddit failure before posting can use the
existing plain-text fallback; an unacknowledged attempted post is left pending.

Anniversary events retain the `r2t_anniversary_date`,
`r2t_anniversary_delivery` and `r2t_anniversary_run` records. Cached first-sent
dates, explicit overrides, February 29 handling and active-channel checks match
the reference. A pending part is claimed with an attempt ID. Explicit Telegram
rejections return it to pending; ambiguous requests remain uncertain. An
inherited sending state is never automatically resent. Prior interrupted run
records and sweep leases remain compatible across language handoffs.

## Build and live-validation boundaries

Release compilation runs on GitHub Actions with Rust 1.99.1, a checked lockfile,
thin LTO and one codegen unit. The artifact contains compiler/source/profile
metadata and a SHA-256 receipt. Compilation and `--describe` use no application
credentials or application requests.

The live trial must still establish observed delivery, resource usage, errors,
backlog and stability. It cannot prove behavior for branches not encountered in
that day. Preserve the original run deadline and record interruptions or workload
differences; do not substitute CI observations for live measurements.

Tokio provides bounded asynchronous jobs instead of Python executor threads.
Driver, TLS, allocator and Sentry implementations differ and are part of the
deployed implementation being compared. Sentry reports safe native error
categories instead of credential-bearing transport strings. These differences
must not be described as an isolated language-speed experiment.
