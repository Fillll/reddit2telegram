# Runtime handoff procedure

The experiment order is Python 3.12, Python 3.15, Rust, Swift, C++, C, Go.
Each label has one fresh window capped at 86,400 seconds. Preparation and a
graceful transition are outside those windows. Never restart a label, extend
its deadline, run two consumers, or substitute a replay observation.

## During the current window

Keep production source, dependencies, configuration, history and schedule
unchanged. Work in isolated topic worktrees and keep implementation/reporting
PRs unmerged. Build native releases remotely. A build or `--describe` check is
not a performance observation and must not load credentials or issue app work.

Poll the actual collector service and fresh observations when checking status.
A running manifest, a deadline or an observation timeout alone does not prove
that a process stopped. Recheck the same service/PID after a transient failure;
do not replace a still-running collector merely because observation expired.

`watch_window.py --directory /absolute/path/to/run --minutes 60` polls the
actual worker and both observer services plus fresh data once per minute. It
checks the selected executable and initial worker PID, emits read-only health
snapshots, and returns a verified-wait checkpoint or a request for inspection.
It never repairs or restarts anything. `--once` is a bounded preflight. A worker
identity change must be reviewed and recorded before acknowledging a new PID;
do not edit the original manifest to hide a restart.

## At the absolute deadline

Wait for the existing collector to finalize its manifest and ledger. Inspect
its summary, last sample, boundary lateness, errors and notes. Retain gaps,
incomplete jobs and interruptions; do not repair them by repeating the window.
The supplementary process sampler has the same absolute cutoff. Production
continues normally after observation stops.

Before deployment, verify that the next label has no ledger entry and that no
other label remains active. Keep the original raw run directory immutable
apart from explicit appended operator notes and reproducible summary exports.

## Prepare the checked release

1. Fetch the current default branch. Review the implementation's complete
   diff, including all scheduled custom behavior, and preserve unrelated
   production modifications in a private backup.
2. Refresh the implementation branch against the current base and reconcile
   its single release increment and changelog with that base. A previous
   checked head/artifact does not cover a new head. Do not overwrite prior
   release history or bundle unrelated production patches.
3. Run release validation and the required release checks. Wait for relevant
   current-head checks and remote native packaging, then inspect that exact
   artifact locally using only `--describe`. Verify its checked source,
   compiler, dependencies, literal hashes, executable checksum and linkage.
   Packaged C/C++/Swift artifacts must load without LD_LIBRARY_PATH overrides.
   Go must retain cgo-free static linkage.
4. Review the exact checked PR head again and merge with a guarded squash or
   merge operation. Record both the checked build head and resulting merge
   commit; they need not have the same SHA. Fast-forward production while
   preserving its existing unrelated modifications. If Git refuses because
   of overlapping edits, reconcile those edits from the private backup rather
   than discarding them or forcing the update.

Follow AGENTS.md for every PR/release operation. Initial prepared versions are
relative to the initial base; they are not a reason to skip the base refresh.
Keep the report-tooling PR isolated until its own appropriate merge boundary.

## Select and drain

Write `state/runtime.json` atomically with the next label, absolute consumer
and scheduler argv, and credential-free runtime/build receipts. Use the same
production YAML, cron file and MongoDB history. Include the native `--describe`
metadata under `describe`, its checksum, the checked source head and merge
identity so the final report can distinguish the executable from its checkout.
For Python, record the actual interpreter/compiler, GIL/JIT state and recognized
build features; retain the pinned package receipt. The measurement interpreter
and its dependencies stay fixed across configurations and are distinct from
the selected application's runtime.

Python consumer/scheduler argv use the prepared interpreter plus the production
entry-point files. Native argv use the checked executable followed by
`consumer` or `scheduler`, `--config` and the absolute production YAML path.
Do not put credentials or raw URLs in runtime metadata.

The dispatcher execs the selected application before Python app imports. The
existing service is configured to restart the consumer. Signal its current
owned MainPID with SIGTERM and let it stop claiming and drain its jobs. Poll
that PID/service until it exits and the replacement has started. A short
observation timeout is not a failed drain. Do not force-kill jobs or issue a
service restart to shorten it. Sending SIGTERM directly to the owned process
allows its drain to finish without starting the service manager's stop timeout.

Only one consumer may exist during the transition. Scheduler jobs queued in
the gap use the same persisted schema. Record the actual gap; it is not part
of either measured window and does not extend the previous one.

## Begin the next fresh window

Confirm the new MainPID resolves to the exact selected executable and that no
old consumer remains. Check service health and runtime metadata. Start the
runner once for the new label with the fixed measurement interpreter. The
runner checks the selected executable and commits the one allowed ledger
entry. Never try a second start after an uncertain launch without inspecting
the existing service and authoritative state first.

Immediately attach `process_sampler.py` to that new directory in its own user
service outside the scheduler accounting slice. Use the original manifest's
deadline, a per-run lock and restart-on-failure behavior that cannot extend it.
Verify both collector handles and fresh samples. Record the transition/build
receipts and sampler source checksum in private operator notes/checkpoints.

The first jobs may have begun before observation; keep their boundary
censoring visible. Kernel lifetime peaks must not be relabeled as window peaks.

## After the last window

Keep production running. Reconcile all seven actual outcomes and inspect raw
coverage, errors, notes, source changes and workload differences. Run the report
arithmetic verifier against the original fresh inputs, then render the PNG and
portable summaries. Inspect the actual exported image and affected panels for
legible values, clipping and retained caveats. Preserve the Python 3.12 cron
incident, partial process-role coverage, body-counter scope, censored jobs,
runtime/library differences and any later interruptions.

Publish only reviewed aggregate/build receipts and the requested final report
under `implementations/benchmarks/results/` through a refreshed, checked PR.
Do not commit raw logs, credentials, process/job IDs, arguments, URLs or media.
The goal is complete only when the requested live runs and final verified
single-image report are actually delivered.
