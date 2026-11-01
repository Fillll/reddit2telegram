# Go source coverage review

The reference is deployed Python 3.12 revision `64bd864`, including the
preserved local supplier/retry/error-policy patches fingerprinted in the fresh
baseline run. This maps scheduled behavior to Go source. Source review, vetting
and compilation do not prove live delivery or exercise unencountered paths.

| Reference behavior | Go source |
| --- | --- |
| Cron TSV/masks, randomized insertion and per-job configuration hydration | `queue.go` |
| MongoDB task states 1–5, atomic claims, whole batch before submission, bounded pending jobs and workers | `queue.go`, `database.go` |
| Five-second blocking waits, signal wakeup, startup recovery, 25-minute expiry and drain on exit/error | `queue.go` |
| Original 60-second RSS check and unused-memory release threshold | `queue.go`, `main.go` |
| Official pooled MongoDB driver, command order, typed dates/ObjectIds and lossless 64-bit cursors | `database.go`, `model.go` |
| Reddit OAuth, quota pacing, transport attempts, ten consecutive listing failures, hydration and candidate limits | `reddit.go`, `queue.go` |
| DB/literal rules, weighted source and promotion cache/order | `channels.go`, `assets` |
| Text/photo/GIF/video/gallery/Imgur/link/crosspost classification and delivery | `classify.go`, `sender.go` |
| Unicode code-point text limits and whitespace, gallery ordering, URL normalization, filters and Markdown fallback | `classify.go`, `model.go`, `sender.go` |
| Streaming MD5, duplicate/history/error checks and sent/rejected records | `sender.go` |
| 50 MiB media caps, two video slots, unique temp directories, exact ffmpeg stream-copy arguments and 60-second timeout | `sender.go` |
| Owner intake, forwarding, update cursor, prefixed normalization and persisted conversation | `maintenance.go` |
| Cleanup/task statistics, weekly growth, public inventory and paginated directory | `maintenance.go` |
| Subscriber/admin sweep, original delays, thresholds queued before snapshots, totals and stable leaderboards | `achievements.go` |
| Milestone history, per-part acknowledgment, fallback rules and forwarding checkpoints | `achievements.go`, `durable.go` |
| Birthday override/cache, first successful post, leap-day handling and yearly uniqueness | `anniversaries.go` |
| Frozen UTF-16-bounded directory, atomic attempts, explicit rejection retries and ambiguous-send holds | `anniversaries.go`, `durable.go` |
| Two-hour sweep leases, owner selectors, renewal/release and interrupted prior owners | `durable.go`, `anniversaries.go` |
| Safe bounded Sentry envelopes and developer reports | `reporting.go` |
| Schema-1 timing, decoded HTTP body counts, acknowledged delivery mix and post hashes | `metrics.go`, `http.go` |

The scheduler uses the full live schedule. Rules, history and durable records
use the same MongoDB database. Embedded JSON assets contain literal source
configuration, not historical or replay input. All application logic is Go;
only ffmpeg and the existing vnstat utility are child commands. No Python
worker or another implementation executable performs its work.

MongoDB commands preserve their command-name field first, BSON dates/ObjectIds
and 64-bit cursor IDs without floating-point conversion. Worker count, pending
limits, batch size, five-second poll interval, two video slots and media/retry
policies retain the deployed settings. Workers drain before shared clients and
reporting resources close, including after a queue database failure.

Durable documents retain existing IDs/kinds/dates, leases, acknowledgment
arrays, forwarding IDs and completion flags. An acknowledged part is persisted
before the next send. Inherited anniversary `sending` becomes `uncertain` and
is held. Explicit Telegram rejections can become pending again. Removed
channels retain their queued anniversary records without receiving new sends.
Milestone fallback distinguishes unavailable source data from an exception
after an unacknowledged posting attempt.

HTTP/1 clients use the reference's connect/read timeout values, streaming
downloads/digests/uploads and keep-alive pools. Idle connections have no active
request read deadline. Body counters measure consumed decoded entity bytes,
matching Python's iter_content definition; TLS framing and Telegram's own URL
downloads remain outside this counter. Upload producer/body cleanup completes
before final job metrics, including early request rejection. Native automatic
HTTP resend header writes and redirects are counted at their transport hooks.

The checksum-pinned toolchain is Go 1.27.3 with the default optimizing compiler,
trimpath, stripped debug tables and cgo disabled. Dependencies include the
official MongoDB v2.9.2 driver and stable YAML v3.0.6; go.sum pins transitive
modules. Artifact receipts contain checked source, compiler, module versions
and sums, literal hashes and executable checksum. The complete source compiled
and passed vet checks before application roles were enabled. Inspect the exact
enabled artifact and its static linkage before handoff.

The Go runtime uses goroutines, its own garbage collector and native HTTP/TLS.
The libc malloc-arena setting is validated for compatible configuration but
does not control this cgo-free implementation. The corresponding periodic
unused-memory release uses debug.FreeOSMemory at the original RSS threshold;
it includes a garbage collection and differs from libc malloc_trim. Record
these differences, compiler/library choices, unobserved branches, interruptions
and sequential-day workload differences in the final image and summaries.
This experiment compares deployed implementations, not isolated language speed.

Keep the draft unmerged during preceding measurement windows. Refresh the
latest base/release notes, review the checked head and inspect artifact identity
before its single fresh 24-hour production window. Build/metadata checks make
no app requests and are not benchmark observations. Do not repeat or extend
the live window.
