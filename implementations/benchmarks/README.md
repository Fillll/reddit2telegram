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
