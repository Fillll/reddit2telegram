reddit2telegram
===============

[![](https://img.shields.io/badge/Telegram-Group-blue.svg)](https://t.me/r_channels)
[![](https://img.shields.io/badge/Telegram-Channel-blue.svg)](https://t.me/reddit2telegram)

Hi there!

These bots just send latest hot submissions from subreddit **/r/%subreddit%** to telegram channel **@r_%subreddit%** hourly. For example [/r/gifs](https://www.reddit.com/r/gifs/) → [@r_gifs](https://t.me/r_gifs).

If you want to obtain your own channel for `/r/%subreddit%`:

1. Create new public telegram channel `@r_%subreddit%`.
2. Add [`@reddit2telegram_bot`](https://t.me/reddit2telegram_bot) as administrator to this channel.
3. Make a pull request to this repo with new script to make posts (use [`reddit2telegram/channels/r_funnny/app.py`](https://github.com/Fillll/reddit2telegram/blob/master/reddit2telegram/channels/r_funny/app.py) as draft), and the tags related (create a tags.txt containing at least 3 tags, separated by spaces and starting with #).
4. Then I will make it alive :)
5. For any questions do not hesitate to contact me in [@r_channels](https://t.me/r_channels) group.


If you appreciate it
--------------------

Patreon: [donate](https://www.patreon.com/reddit2telegram)


Currently alive channels
------------------------

Complete list of all active channels (more than 800) is available at our channel [@reddit2telegram](https://t.me/reddit2telegram).


This is a pet-project 🐶
------------------------

Which means you really shouldn't expect much from it. I wrote it over the weekend to solve my own pain. No state-of-art kubernetes bullshit, no architecture patterns, even no tests at all. It's here just to show people what a pet-project might look like.

This code has been written for fun, not for business. There is usually a big difference. Like between riding a bike on the streets and cycling in the wild for fun :)

_© from [infomate.club](https://github.com/vas3k/infomate.club)_



Running it
----------

Easiest way is to ask for new channel at [@r_channels](https://t.me/r_channels). Or follow the manual as stated above. :)

But if you are geek enough then install mongodb, ffmpeg, python and setup cron:

```cron
46 * * * * /root/reddit2telegram/auto_update.sh
* * * * * /root/reddit2telegram/reddit2telegram/cron_thread_job.sh
```

When tidying the main-run schedule in `reddit2telegram/own.cron`, start at
minute 45 with one main run, then two at 44, three at 43, and so on. Move only
the excess runs backward and stop as soon as earlier gaps absorb them; do not
redistribute the rest of the hour. The current adjustment covers minutes 34–45.
A channel's main run is the earliest minute in its first schedule row; other
minutes and subsequent rows are extra runs. Preserve those extra schedules,
`tech_*` jobs, and each channel's run frequency and calendar restrictions.

Versions and contributions
--------------------------

`VERSION` records the current stable version, starting at **1.0.0**. See
[Changelog.md](Changelog.md) for release notes. Every change goes through a PR,
including maintenance and channel additions. Maintainers may merge their own
PRs after validation; direct pushes to `master` are prohibited.

The compatibility contract covers documented CLI arguments and configuration,
persisted MongoDB formats requiring migration, and established posting behavior.
Following [SemVer](https://semver.org/), incompatible changes increment major,
compatible new features/channels and deprecations increment minor, and compatible
fixes and maintenance increment patch. Each PR makes one release increment and
includes one `SemVer: major`, `SemVer: minor`, or `SemVer: patch` line in its body.
The initial release PR uses `SemVer: bootstrap`.

On a fresh topic branch, prepare and validate a release:

```bash
git config core.hooksPath scripts/hooks
git fetch origin
git switch -c fix/example origin/master
python3 scripts/release.py bump patch --summary 'Describe the change for operators.'
python3 scripts/release.py validate --base-ref origin/master --bump patch
python3 -m unittest discover -s tests -p test_release.py
git push -u origin HEAD
```

Include `VERSION`, `Changelog.md`, and the implementation in the PR. Refresh the
bump if another release merges first. Use squash or merge commits. After a
validated PR merges, GitHub Actions publishes the matching `vX.Y.Z` tag and
release notes; existing tags are immutable.
Release checks use no application credentials and never send Telegram messages.

Tests
-----

The consumer keeps at most `consumer.max_pending` submitted jobs (default: pool
size). Two video jobs may download, mux, and upload concurrently. Uploads stream
from disk, and every attempt removes its private files before returning a
pipeline slot, including oversized rejections and interrupted uploads. Media
HTTP sessions close after each job; verified TLS contexts are shared across
connections. On glibc systems,
`pool.malloc_arenas` defaults to four to reduce memory retained by native
allocation pools. Once per minute, a consumer above 256 MiB collects dead job
cycles and returns unused native heap pages to the OS. SIGTERM/SIGINT stop new
claims and drain submitted work.

Reddit listings retain at most 25 candidates per page, while still scanning the
configured total candidate limit. Media classification uses cached listing
fields so absent gallery/crosspost fields do not fetch full comment trees.

Resource monitoring includes the worker, ffmpeg children, and cgroup file cache.
The kernel peak catches spikes between samples. These targets use decimal bytes:
500 MB during normal operation and 1 GB during spikes. Run a single sample from
cron, or add `--seconds 86400 --interval 5` for a full-day observation:

```bash
python3 scripts/monitor_resources.py --log logs/service_resources.jsonl
```

Offline tests exercise real local TLS and a 49 MiB multipart upload without
production credentials. Install test dependencies with
`python -m pip install -r requirements.txt -r tests/requirements.txt`.
For a fresh checkout, copy `tests/offline-config.yml` to
`reddit2telegram/configs/prod.yml` before `python -m pytest -q`. GitHub Actions
does this automatically; live tests remain disabled.

Live integration tests send real messages to `@r_channels_test` and use Reddit API.

```bash
R2T_LIVE_TESTS=1 /root/reddit2telegram/.venv/bin/python -m unittest tests/test_live_send.py
```

Live resource regression tests verify actual Telegram message IDs, repeated-job
and exception cleanup, six concurrent video jobs with the two-pipeline limit,
photo/GIF/gallery delivery, video download and audio merging, and live
Reddit-to-Telegram supply. They generate media locally and serve video inputs
on loopback; Telegram receives real uploads. Messages are paced, and media files
are isolated from production's temporary-file cleaner. All sends target
`@r_channels_test`; the configured bot must have posting rights there.

```bash
R2T_LIVE_TESTS=1 .venv/bin/python -m unittest tests/test_live_resources.py -v
```

Leave `R2T_LIVE_TESTS` unset during offline test runs.

Anniversary announcements
------------------------

`tech_anniversary` runs daily at 11:55 UTC without fetching a Reddit listing.
On a channel's anniversary, its introduction features `@reddit2telegram`, then
the `@r_channels` community, followed by the birthday greeting and a paginated
directory of other scheduled channels. A short birthday notice also goes to
the main channel, community, and developer chat. Identical destinations are
deduplicated. Announcements use text, so unavailable Reddit media cannot block
them.

The default anniversary date is the earliest **successfully sent** post in
`urls`, never the start of statistics collection. This is an earliest-known-post
date, not a verified Telegram creation date. It is saved once in `settings`
under `_id: r2t_anniversary_date:<lowercase channel>` so history cleanup cannot
move it. A channel document's optional `anniversary_date` (`YYYY-MM-DD` or a
BSON datetime) overrides that default. Channels without either date are skipped
and reported; one missing or invalid channel does not prevent other sends.
February 29 anniversaries are observed on February 28 in non-leap years.

Annual delivery records use `_id: r2t_anniversary_delivery:<channel>:<UTC year>`
in `settings`. Their message text and directory order are frozen when queued;
each acknowledged Telegram message ID is saved before the next send. Daily
runs resume outstanding messages from earlier days and never repeat completed
parts. Channels removed from the schedule are not sent queued retries. Every
invocation also leaves a `kind: r2t_anniversary_run` record containing its start,
finish, outcome, due/completed/pending counts, missing history, and errors. The
next lease owner marks a crashed sweep as interrupted. The hourly task cleaner
does not remove any of these records. No historical
anniversaries are backfilled on installation.

Inspect dates, upcoming/due channels, a complete message preview, pending parts,
and the last seven days of run history without writing state or sending messages:

```bash
.venv/bin/python scripts/anniversary_report.py
.venv/bin/python scripts/anniversary_report.py --date 2027-02-12 --days 30
```

A sweep lease prevents overlapping workers. Telegram API rejections are safe to
retry, while timeouts and interrupted requests are recorded as `uncertain`.
Telegram does not provide an idempotency key for sends, so these parts require
checking the destination before another attempt. After that check, an operator
can conditionally update the event in `settings`: select its `_id` and
`deliveries.<index>.state: uncertain`; set that part's state to `sent` and its
`message_ids` to the verified IDs if it arrived, or reset it to `pending` if it
did not. The next scheduled run resumes the remaining parts. A partial run is
reported as a supply failure, with the retained run ID for diagnosis. The
existing `supplier.py --test --sub tech_anniversary` path sends only a sample to
`@r_channels_test` and leaves production anniversary records untouched.
