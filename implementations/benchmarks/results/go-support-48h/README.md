# Go: two days of live support checks

[Open the final picture](go-support-48h.png).
[Inspect the aggregate data](support-summary.json).
[Verify the exported file hashes](render-receipt.json).

The separate production observation ran for exactly 172,800 seconds, from
**12 November 2026 07:13:56.438214 UTC** to
**14 November 2026 07:13:56.438214 UTC**. The original measurement bounds were
retained. The Go worker was already running for 86.52 hours at launch; its
identity, executable, source, configuration and schedule remained unchanged during
the window. Both collectors stopped successfully. The production worker
continues its normal schedule.

## Live support outcomes

- **Anniversaries:** five naturally due events completed, with 65 acknowledged
  delivery parts and persisted checkpoints. Each new part has one attempt.
  Both anniversary sweeps remain partial because five older events contain
  17 uncertain parts. All 65 parts of those older events stayed unchanged:
  17 uncertain, 45 pending and three already sent. They were not reset or resent.
- **Subscriber milestones:** natural 199→200 and 2→3 crossings each completed
  an announcement and its forward, with one attempt and both checkpoints saved.
  Their attempts and checkpoints remained unchanged in subsequent observations.
- **Statistics:** eight sweeps started and seven completed successfully within
  the window. The last sweep was still running at cutoff and is censored.
  Success describes the task outcome; completed sweeps also recorded API errors.
  The final bounded snapshot contains 6,397 rows with numeric subscriber counts
  and document timestamps inside the window. These include boundary sweeps;
  document timestamps are not MongoDB commit times.
- **Cleanup:** all 48 scheduled runs completed successfully.
- **Channel intake / receiver:** all 48 scheduled runs failed with a database
  error. The production nonunique `setting_1` index conflicts with the Go
  receiver's unique-index request; the same command reproduced MongoDB code 86
  in isolated live state. Individual production error codes were not captured.
  The index was left unchanged during measurement. Direct controlled intake
  passed; production inbound polling remains failing and unvalidated.
- **Weekly summary:** no production slot fell inside the fixed window.
  The weekly summary and directory were sent through a controlled live case.

Nine controlled native cases passed, with **20 real `sendMessage`
acknowledgements and one `forwardMessage` acknowledgement**, all restricted to
`@r_channels_test`. They exercised anniversary pagination and resume, yearly
deduplication, uncertainty holds, milestone crossing/fallback/forward resume,
current Reddit candidate selection, weekly delivery, direct intake, the index
conflict and isolated cleanup. Test data and delivery records used separate
MongoDB databases. The directory case used a read-only snapshot of 830 current
public entries. No production bot updates were polled by the tests.

These cases used a separately compiled build of the production Go package with
test-only destination routing and an outbound guard. They are distinct from the
unchanged production worker's natural events. Compilation ran in GitHub Actions;
live execution used local credentials. The first artifact's application linker
label remained `unbuilt`; its checkout and binary were verified externally.
Later artifacts additionally embedded the checked revision. The aggregate JSON
retains the checked build revisions, workflow identifiers and artifact hashes.

## Measurement and interpretation

The window recorded **41,309 job ends: 39,454 successful and 1,855 failed**,
plus 26 starts without an observed end. The 31,729 whole-job Telegram
acknowledgements include posts, support messages and error notices; they are not
a count of unique posts or proof that every channel succeeded. Recorded failure
classes, API errors and rate limits remain in the image and aggregate data.

The picture includes average, median, nearest-rank P95 and sampled maximum for
CPU, memory, job duration and queue wait. Application CPU averages **6.50% of one
core**. Application cgroup memory averages **71.01 MiB**, including file cache;
worker process RSS averages **26.21 MiB**. Memory growth coincides with increased
file cache, but this observation does not establish its cause or prove a leak.
File cache and process RSS describe different scopes and should not be added.

There are 34,560 eligible primary samples and 34,560 supplementary process
samples. One post-cutoff primary read is excluded. Application CPU interval
coverage is 99.9971%, displayed rounded in the picture. Three process samples
with unreadable processes are excluded from process distributions; one
decreasing MongoDB CPU-counter interval is excluded from MongoDB and combined
CPU statistics. Missing values remain missing. Sample maxima are not lifetime
kernel peaks. Timing distributions use paired in-window starts and ends, so
boundary work is censored rather than allowed to extend the measurement.

Controlled checks and read-only observation shared the host, MongoDB service
and bot quota. Test processes were outside application accounting; shared
contention and database costs remain included. This is a Go-only functional
follow-up, with no historical performance comparison or new Rust-versus-Go
ranking. The earlier 24-hour report and all eight earlier windows were preserved.

Independent arithmetic reconciled CPU counters and distributions, all component
memory measures, process RSS, paired timings, job outcomes, request counters,
support coverage and delivery checkpoint counts against a private frozen copy
of the actual observations. Its input hashes match the rendered summary.
The actual final image was inspected for legibility, clipping and numerical
agreement. Raw runtime records, credentials, private identities and message IDs
remain outside Git; only aggregate results and their hashes are published.
