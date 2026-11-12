# Go support live checks

These opt-in functional checks complement the separate 48-hour Go production
observation. They are not performance samples and do not replace naturally
scheduled production jobs or prior comparison windows.

GitHub Actions only compiles an artifact, without credentials or application
traffic. The staging script copies the Go package into a new temporary directory,
redirects the two hardcoded announcement constants to `@r_channels_test`, and
inserts a test-only outbound guard at the Telegram API boundary. It does not edit
the production package. The receipt records the source revision and original and
staged file hashes; formatting happens after staging. The application support
logic otherwise comes from the checked source revision.

The local test requires `R2T_LIVE_TESTS=1`, an absolute local credential path in
`R2T_LIVE_CONFIG`, and an absolute private JSONL path in `R2T_LIVE_RECEIPTS`.
The guard permits only the test channel handle, or its numeric ID after a live
`getChat` identity check. It rejects `getUpdates`, uploads, arbitrary destinations
and unknown methods. Credentials and runtime evidence must stay out of Git and CI.

The harness creates a unique `r2t_live_support_*` MongoDB database and a temporary
cron fixture. It retains isolated database evidence. It never resets production
delivery state or changes production indexes. Cases cover:

- Anniversary delivery with persisted acknowledgements, yearly deduplication,
  resumption without duplicate sends, and inherited uncertainty holds.
- Milestone crossing with a real current subscriber count and a controlled
  previous count and threshold; text fallback, checkpoint persistence and
  forwarding/resumption within the same test channel. Reddit candidate selection
  is excluded from this controlled fallback case.
- Weekly summary and directory delivery using controlled isolated statistics.
- Receiver index-conflict reproduction in isolated MongoDB, plus direct channel
  intake and real test-channel replies. Production inbound polling is excluded.
- Cleaner deletion and status bookkeeping using only isolated temporary files
  and task records, followed by a real test-channel summary.

Controlled counts, dates and fixture histories are labeled as such; a passing
case does not prove a milestone or anniversary occurred organically. Test API
attempts are recorded separately from production job acknowledgements. Run the
artifact in its own service, outside the measured worker/scheduler cgroups, and
retain its start/end times: it shares the host, MongoDB and bot quota with the
production observation, which must be disclosed in the follow-up report.
