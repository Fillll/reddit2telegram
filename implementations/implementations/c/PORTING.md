# Plain C source coverage review

The reference is deployed Python 3.12 revision `64bd864`, including the
preserved local supplier, retry and error-policy patches fingerprinted in the
fresh baseline run. This maps scheduled behavior to C source. Compilation and
source review do not establish live performance or exercise unencountered paths.

| Reference behavior | C source |
| --- | --- |
| Cron TSV/masks, randomized insertion, configuration hydration | `queue.c` |
| Atomic MongoDB claims, task states 1–5, batch claim before submission, bounded pending jobs and fixed workers | `queue.c`, `database.c` |
| Five-second blocking wait, signal wakeup, startup recovery, 25-minute expiry, drain on exit/error | `queue.c`, `platform/interop.c` |
| Arena limit and periodic RSS-triggered allocator maintenance | `main.c`, `queue.c` |
| Pooled MongoDB commands, typed BSON dates/ObjectIds, lossless 64-bit cursor IDs | `database.c`, `model.c`, `platform/interop.c` |
| Reddit OAuth, quota pacing, transport retries, ten consecutive listing failures, hydration and candidate limits | `reddit.c`, `queue.c` |
| DB/literal channel rules, weighted source, promotions and formatting | `channels.c`, `assets` |
| Text/photo/GIF/video/gallery/Imgur/link/crosspost classification and delivery | `classify.c`, `sender.c` |
| Unicode code-point text limits, gallery ordering, URL normalization, filters and Markdown rejection fallback | `classify.c`, `model.c`, `sender.c` |
| Streaming MD5, duplicate/post/error history and sent/rejected records | `sender.c` |
| 50 MiB media caps, two video slots, unique temporary directories, exact ffmpeg stream-copy arguments and 60-second timeout | `sender.c`, `process.c` |
| Owner-only channel intake, forwarding, update cursor, normalization and persisted conversation | `maintenance.c` |
| Cleanup/task statistics, weekly growth, public inventory and paginated directory | `maintenance.c` |
| Subscriber/admin sweep, original delay coefficient, thresholds queued before snapshots and summaries/leaderboards | `achievements.c` |
| Milestone history, per-part acknowledgments, fallback rules, forwarding checkpoints | `achievements.c`, `durable.c` |
| Birthday override/cache, first successful post, leap-day handling, yearly uniqueness | `anniversaries.c` |
| Frozen UTF-16-bounded directory, atomic attempts, explicit rejection retries, ambiguous-send holds | `anniversaries.c`, `durable.c` |
| Two-hour sweep leases, owner selectors, renewal/release and interrupted prior owners | `durable.c`, `anniversaries.c` |
| Safe Sentry envelopes and developer reports | `reporting.c` |
| Schema-1 timing, HTTP body counters, acknowledged delivery mix and post hashes | `metrics.c`, `http.c` |

The scheduler reads the full live schedule. Normal rules and posting history
come from the same live MongoDB database. JSON assets contain literal source
configuration, not historical traffic. The platform module wraps C libraries
and operating-system APIs; all application logic is C. No Python worker or
another implementation executable performs its work.

Owned JSON locals use Jansson's documented GCC/Clang scope cleanup. Typed
builders consume owned values; retaining a borrowed node is explicit. Errors
return normally through cleanup scopes. Acknowledgment contexts outlive their
synchronous sender calls, and sender clones borrow clients from the live root
sender. The fixed worker pool drains before root resources are destroyed. The
bounded reporting thread retains its state if its two-second shutdown wait
expires. There is no longjmp bypassing cleanup or C++ exception machinery.

Durable documents retain the existing IDs, kind names, dates, leases,
acknowledgment arrays, forwarding IDs and completion flags. Each acknowledged
part is persisted before another send. Interrupted anniversary `sending`
becomes `uncertain` and is held. Explicit Telegram rejections can become pending
again. Milestone fallback distinguishes missing source data from an exception
after an unacknowledged attempted post. Removed channels retain their pending
anniversary records without receiving new sends.

Remote release compilation and packaging passed for the complete source before
the completion guard was enabled. Builds use checksum-pinned LLVM/Clang 23.1.4,
GNU C17 (scope-cleanup extensions), `-O3 -DNDEBUG` and thin LTO. Jansson,
libmongoc/libbson, libcurl/OpenSSL, libyaml and pthreads supply native libraries.
The artifact includes required non-glibc dynamic libraries with transitive
DT_RPATH, system-package receipts, compiler/source/literal hashes and an
executable checksum. Inspect the exact enabled artifact without environment
overrides before handoff. Compilation and `--describe` make no app requests.

The live window still needs to establish observed delivery, resource use,
backlog, stability and errors. Library choices, native threads, allocator
behavior and safe native error categories differ from Python. This experiment
compares deployed implementations; it cannot isolate language speed or ensure
identical workloads on sequential live days. Disclose unobserved paths and
interruptions in the final single-image report and supporting summaries.

Keep the draft unmerged during preceding windows. Refresh base/release notes,
review the checked head and inspect artifact identity before the single fresh
24-hour production window. Do not repeat or extend it.
