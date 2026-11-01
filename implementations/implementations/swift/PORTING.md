# Swift source coverage review

The reference is deployed Python 3.12 at `64bd864`, including the preserved
supplier/retry/error-policy patches fingerprinted in its fresh measurement.
This is a source review and compilation record, not a live performance result.

| Reference behavior | Swift source |
| --- | --- |
| Cron TSV, five-field matching, randomized batch submission and job config hydration | `Queue.swift` |
| MongoDB task statuses 1–5, atomic claims, batch-before-submit, bounded workers/pending tasks | `Queue.swift`, `Database.swift` |
| Five-second blocking wait, signal wakeup, 25-minute expiry, startup recovery, drain on exit/error | `Queue.swift`, `CR2T/interop.c` |
| Existing allocator arena limit and periodic RSS-triggered trimming | `main.swift`, `Queue.swift`, `CR2T/interop.c` |
| YAML, pooled MongoDB commands, extended JSON IDs/dates and 64-bit cursor IDs | `Model.swift`, `Database.swift`, `CR2T/interop.c` |
| Reddit password OAuth, quota pacing, transport attempts, ten consecutive listing retries and configured limits | `Reddit.swift`, `Queue.swift` |
| Authenticated hydration for missing cached submission fields | `Reddit.swift`, `Sender.swift` |
| DB/local channel rules, weighted source selection, promotions and nice-post formatting | `Channels.swift`, literal `Assets` |
| Text/photo/GIF/video/gallery/Imgur/link/crosspost handling, filters, templates and Markdown fallback | `Sender.swift` |
| Code-point text/caption boundaries; gallery ordering and URL normalization | `Sender.swift` |
| 50 MiB limits, two video slots, streaming downloads/uploads, exact ffmpeg stream-copy command and 60-second timeout | `Sender.swift`, `HTTP.swift`, `CR2T/interop.c` |
| Duplicate streaming MD5, history/error thresholds, rejected/sent URL records | `Sender.swift` |
| Owner-only channel intake, cursor, forwarding and persisted conversation | `Maintenance.swift` |
| Cleanup/task counts, weekly growth/directory report and existing operator text | `Maintenance.swift` |
| Subscriber/admin sweep, existing delay coefficient, thresholds queued before snapshots, totals and gain/fall reports | `Achievements.swift` |
| Milestone history, pending retries, per-message acknowledgments and forwarding checkpoints | `Achievements.swift`, `Durable.swift` |
| Stable birthday cache/override, first successful post, February 29 handling and yearly uniqueness | `Anniversaries.swift` |
| Frozen UTF-16-bounded directory, attempt claims, explicit rejection retries and ambiguous-send holds | `Anniversaries.swift`, `Durable.swift` |
| Two-hour sweep leases, renewal, prior-owner interruption records and run outcomes | `Durable.swift`, `Anniversaries.swift` |
| Sentry and developer error reports without credential-bearing transport text | `Reporting.swift` |
| Schema-1 job timing, message mix, HTTP body counters and posting hashes | `Metrics.swift`, `HTTP.swift` |

No known scheduled task is replaced by an empty success implementation. The
application uses the live schedule and live MongoDB channel/history records.
The JSON assets are source-defined configuration literals, not replay inputs.
The C module is library/platform interop; scheduling and application behavior
execute in Swift without another implementation's executable or a Python worker.

Durable settings retain the Python kind names, identifiers, lease fields, frozen
delivery records, acknowledgment arrays and completion fields. An inherited
anniversary `sending` state becomes `uncertain` and is never automatically resent.
Checkpoint callbacks persist each acknowledged part before further delivery.
Milestone fallback follows the reference: a source failure before posting may
use plain text; an exception after an unacknowledged attempted post leaves the
event pending. Prior posting history prevents repeated milestone creation.

The native build uses the official `swift:6.4.2-noble` image, Swift 5 language mode
and optimized release compilation. The artifact includes the exact compiler,
source commit, C library versions/package receipt, executable checksum, resource
hashes and bundled runtime libraries. Compilation and `--describe` use no
application credentials or application traffic. The live trial still needs to
establish observed delivery, stability, resource usage, errors and queue behavior.
Unencountered branches cannot be claimed as live-validated.

Foundation workers, libmongoc/libcurl/OpenSSL, Swift's allocator/runtime and
Sentry envelope transport differ from the Python deployment. Sentry follows the
documented envelope/event protocol:
<https://develop.sentry.dev/sdk/envelopes/> and
<https://develop.sentry.dev/sdk/event-payloads/>. It reports safe native categories
instead of Python tracebacks. The result compares complete deployed
implementations; it does not isolate programming-language execution speed.

Keep this draft unmerged during preceding measurement windows. Before handoff,
refresh the base/release notes, review the checked head and verify the artifact
identity. Preserve the fixed 24-hour deadline, record interruptions, and do not
replace real observations with compilation output or replay traffic.
