# C++ source coverage review

The reference is the deployed Python 3.12 source at `64bd864`, including the
preserved local supplier/retry/error-policy patches fingerprinted in its fresh
run. This maps the scheduled behavior to C++ source. Compilation and source
review do not establish live performance or exercise unencountered branches.

| Reference behavior | Native source |
| --- | --- |
| Cron TSV, masks, randomized batch submission, job config hydration | `queue.cpp` |
| Atomic MongoDB claims, task values 1–5, claim-before-submit, bounded pending work and workers | `queue.cpp`, `database.cpp` |
| Five-second blocking wait, signal wakeup, startup recovery, 25-minute expiry and graceful drain | `queue.cpp`, `platform/interop.c` |
| Arena limit and periodic RSS-triggered allocator maintenance | `main.cpp`, `queue.cpp` |
| Pooled MongoDB commands, typed dates/ObjectIds and 64-bit cursor IDs | `database.cpp`, `model.cpp`, `platform/interop.c` |
| Reddit OAuth, quota pacing, transport attempts, ten consecutive listing retries, hydration and configured candidate limits | `reddit.cpp`, `queue.cpp` |
| DB and literal channel rules, weighted source and promotions | `channels.cpp`, `assets` |
| Text/photo/GIF/video/gallery/Imgur/link/crosspost delivery and original formatting/filter rules | `sender.cpp` |
| Unicode code-point limits, gallery ordering, URL normalization and Markdown rejection fallback | `sender.cpp`, `model.cpp` |
| Streaming MD5, posting/error history and sent/rejected records | `sender.cpp` |
| 50 MiB media limits, two video slots, unique temporary directories, exact ffmpeg stream-copy command and 60-second timeout | `sender.cpp`, `process.cpp` |
| Owner-only channel intake, update cursor, forwarding and persisted conversation | `maintenance.cpp` |
| Cleanup/task statistics, weekly growth and paginated directory | `maintenance.cpp` |
| Subscriber/admin sweep, original delay coefficient, thresholds queued before snapshots and summary/leaderboards | `achievements.cpp` |
| Milestone history, per-message acknowledgments, fallback rules and forwarding checkpoints | `achievements.cpp`, `durable.cpp` |
| Stable birthday cache/override, first successful post, leap-day handling and yearly event uniqueness | `anniversaries.cpp` |
| Frozen UTF-16-bounded directory, atomic attempts, explicit rejection retries and ambiguous-send holds | `anniversaries.cpp`, `durable.cpp` |
| Two-hour sweep leases, renewal/release, interrupted prior owners and sweep outcomes | `durable.cpp`, `anniversaries.cpp` |
| Safe Sentry envelopes and developer reports | `reporting.cpp` |
| Schema-1 timing, HTTP body counters, acknowledged message mix and posting hashes | `metrics.cpp`, `http.cpp` |

The scheduler reads the complete live schedule, and normal channel rules and
history come from the live MongoDB database. The JSON assets are literal source
configuration. They are not historical traffic or replay fixtures. The platform
module wraps C libraries and operating-system APIs; application behavior is C++
without a Python worker or another language's implementation executable.

Durable records retain the existing kind names, IDs, dates, lease fields,
acknowledgment arrays, forwarding IDs and completion flags. Each acknowledged
part is stored before the next send. Anniversary `sending` inherited from an
interrupted process becomes `uncertain`; it is not automatically resent.
Milestone fallback follows the reference's distinction between unavailable
source data and an exception after an unacknowledged attempted post.

Builds use checksum-pinned LLVM 23.1.4 and nlohmann/json 3.12.0 with C++23,
optimized release flags and LTO. Runtime library/package receipts, compiler and
source identity, literal configuration hashes and an executable checksum travel
with the artifact. Compilation and `--describe` use no app credentials or app
traffic. The full-port execution guard remains disabled until compilation and
artifact review pass; the subsequent live window still needs to establish
observed delivery, stability, errors, backlog and resource usage.

The implementation uses bounded native threads, libmongoc/libcurl/OpenSSL and a
bounded Sentry envelope transport. Libraries, allocator behavior and native
error categories differ from Python and belong to the deployed implementation
being compared. Do not describe the live comparison as isolated language speed.
Unobserved branches, interruptions and real-day workload differences must be
reported in the final report.

Keep this draft unmerged during preceding measurement windows. Refresh the
base/release notes, review the checked head and inspect artifact identity before
handoff. Use only the single fresh 24-hour production window as benchmark data.
