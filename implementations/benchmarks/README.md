# Live implementation experiment

One live measurement window of exactly 86,400 seconds for each configuration:
Python 3.12, Python 3.15, Rust, Swift, C++, C, Go. No replay, simulated traffic,
historical baseline, repeated runs, or extended windows. The final deliverable
includes one high-resolution comparison image, plus inspectable summaries.

Python remains in `reddit2telegram/`. Other languages belong in
`implementations/implementations/{rust,swift,cpp,c,go}/`.

## Workload contract

Only one production consumer implementation may run at a time. Preserve the
MongoDB collections and task status values, channel rules, cron schedules,
poll interval (5 seconds), configured concurrency (32 workers), bounded pending
jobs, two-video pipeline limit, ffmpeg command, retries and timeouts. Preserve
posting history across handoffs. Port custom channel behavior as well as normal
Reddit posting; a Python subprocess is not a native implementation.

The initial production checkout has unrelated local patches. Preserve those
patches; record tracked source hashes, configuration hashes and the dirty diff
hash in each run's manifest. Any baseline with a moving source or configuration
is explicitly flagged. New dependencies, runtime builds and library choices
must be identified, rather than attributing every difference to the language.

## Measurement contract

An external runner records resources every five seconds, with cumulative CPU
counters at both boundaries. Production keeps running after measurement stops.
No run can resume past its original deadline. Restarts, missing samples,
incomplete jobs and early termination remain visible in the summary.

Report average, median, p95, maximum, and count for sampled CPU and memory,
processing times and queue delay. Report CPU seconds/completed job, memory
trend, successes/failures, acknowledged Telegram messages by media kind, HTTP
attempts/errors/rate limits, Reddit listing retries, measured request/download
body bytes, descriptors, connections, temporary files, and queue backlog.
Counts are observational: acknowledged messages do not prove absence of every
possible duplicate. Check posting records for observed duplicate deliveries.

Application attribution includes the consumer and ffmpeg children, plus
scheduler executions. MongoDB is reported separately. Benchmark tooling is
excluded. Worker cgroup memory includes file cache. A kernel peak that predates
the window must be labeled as lifetime, never presented as a window peak.
Combined sampled memory and independent component kernel peaks are different
metrics. HTTP body bytes exclude TLS/framing; URL-based Telegram media transfers
performed by Telegram are not network traffic on this host.

Job events contain only IDs, channel module names, timings, counters and error
class names. Never serialize configuration values, tokens, request URLs,
messages, response payloads, or exception strings. Events use schema version 1:

- `job_start`: task_id, module, queue_wait_seconds.
- `job_end`: task_id, module, status, duration_seconds, queue_wait_seconds,
  counters, error_type (class name only).
- `scheduler_end`: wall_seconds, status.
- `scheduler_submitted`: submitted_jobs.
- `post_record`: task_id, post_key (SHA-256 of channel and source URL).

The scheduler's CPU and memory are measured externally from its dedicated
systemd slice; its event records exit status and wall time. Short-lived scheduler
processes and children remain accounted in cumulative slice counters.

Runtime control and raw data are local-only in ignored `state/` and `runs/`.
`results/` contains only curated, reviewed summaries and the final report.

### Supplementary process observations

`process_sampler.py --directory /absolute/path/to/run` observes only the worker
cgroup and its existing processes. It never starts application work, changes
the schedule or extends a window. Run it in its own user service, outside the
scheduler accounting slice, immediately after each new window begins. It holds
a per-run lock, appends observations across a crash restart and always retains
the original deadline.

The Python 3.12 supplement began partway through its window; earlier process
detail is unavailable. The primary cgroup collector retains its original full
window. Separate process RSS is sampled; short ffmpeg lifetimes can be missed.
Parent reaped-child CPU plus live child CPU includes work between polls, but it
cannot identify every short child's executable. Report that CPU as helpers,
including ffmpeg and maintenance utilities. FFmpeg-specific observed CPU is a
lower bound, not an exact total. These limits belong in the final image.

### Single-image report

The report uses original manifests, samples, events, queue snapshots, notes,
process observations and the experiment ledger. Missing values remain missing.
CPU distributions use valid intervals of at most ten seconds; cumulative CPU
totals can retain monotonic deltas across longer gaps. Post-deadline boundary
reads are excluded. Timings require paired in-window start/end events; counters
describe observed job ends. Memory includes cgroup file cache, and kernel
lifetime peaks remain separate from sampled window maxima.

The common body comparison uses non-Telegram decoded response bytes and
Telegram request bytes. Python does not count Telegram response bodies; the
extra native counters remain available without being added to the common
comparison. Body bytes exclude TLS/framing and remote Telegram URL fetches.

Install plotting wheels into an independent tooling environment, not the
measured production environment:

```sh
python3 -m venv /absolute/path/report-env
/absolute/path/report-env/bin/pip install --only-binary=:all: --require-hashes -r implementations/benchmarks/report-requirements.txt
```

Inspect current evidence without generating a final artifact:

```sh
python3 implementations/benchmarks/report.py --runs /absolute/path/runs --inspect
python3 implementations/benchmarks/verify_report.py --runs /absolute/path/runs --receipt /private/path/arithmetic-check.json
```

The verifier independently reconciles consequential statistics against a
temporary private copy of the fresh live observations; it creates no benchmark
traffic or fabricated inputs. It checks counts, CPU deltas/weighted means,
memory/timing percentiles, backlog, source hashes and window boundaries. Its
receipt states the actual scope, including whether repeated execution IDs
need a separate pairing review. The private raw copy is removed afterwards.

After all seven windows finalize, generate the image and portable evidence:

```sh
/absolute/path/report-env/bin/python implementations/benchmarks/report.py --runs /absolute/path/runs --output implementations/benchmarks/results
```

The renderer refuses an unfinished, repeated or overlapping experiment. It
produces `r2t-live-comparison.png`, `comparison.json`, `distributions.csv`,
`windows.csv`, `counters.csv` and a rendering receipt. The PNG is 4800 by 4400
pixels. Inspect the exported image for readable labels, clipping and faithful
values before delivery; an import/build check does not prove visual quality.
Only allowlisted aggregate/build metadata is exported, not raw process/job IDs,
arguments, configuration values, payloads or URLs. A reviewed portable JSON
bundle can also be rendered with `--bundle /path/comparison.json`.

## Interpretation

All variants use actual Reddit, Telegram and MongoDB. Sequential live days have
different payloads, media, upstream latency and rate limits. Show workload mix
beside resources; report observed implementation performance, not an isolated
language speed ranking. No synthetic performance or missing results may be
substituted for a live observation.

## Operation

After deploying instrumentation and restarting the existing worker, launch the
fresh baseline from the production virtual environment:

```sh
.venv/bin/python implementations/benchmarks/runner.py start --root . --label python312
```

The command installs a user accounting slice and starts a user systemd service
named `r2tbench-python312`. The collector survives client disconnection. A
collector crash resumes against the same absolute deadline; an intentional stop
finalizes an interrupted result. No production worker is stopped at the end.
The ledger refuses a second run for any label. A subsequent implementation may
start only after the previous run has finalized.

`state/runtime.json`, if present, selects consumer and scheduler argv arrays and
a label. The existing system service and cron entry exec the selected native
binary or Python interpreter before importing the Python application. This
avoids requiring administrator service changes or running a Python worker
alongside a native worker. The file is local-only and must contain no secrets.

Implementation work happens in isolated worktrees during a measurement window.
Do not change the measured production checkout, environment, configuration or
schedule until its window ends. Log unexpected deployment/configuration changes
as a limitation instead of silently treating the run as unchanged.
