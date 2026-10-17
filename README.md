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
production credentials. For a fresh checkout, copy `tests/offline-config.yml` to
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
