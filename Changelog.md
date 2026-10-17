# Changelog

All notable changes are recorded here, newest release first. Versions follow
[Semantic Versioning](https://semver.org/). Dates use America/Los_Angeles.
The history before this initial versioned snapshot remains in Git.

## [1.0.3] - 2026-10-17

### Fixed

- Release video temporary files before returning pipeline slots, including
  oversized rejections and interrupted uploads. A sender waiting on later API
  work can no longer retain old media outside the two-pipeline bound.
- Verify immediate cleanup with retained senders and inspect audio/video tracks
  in the file delivered by Telegram after local upload files have been removed.

## [1.0.2] - 2026-10-16

### Fixed

- Use cached listing fields to classify images, text, videos, galleries, and
  crossposts without fetching full post/comment trees for absent optional fields.
- Retain at most 25 candidates per listing page while preserving the configured
  total limit, ordering, and pagination. This reduces per-job metadata allocation.
- Add real-PRAW regression tests and live Reddit-image delivery checks that
  assert classification makes no additional post/comment API request.

## [1.0.1] - 2026-10-16

### Fixed

- Close media HTTP sessions after every job and share a verified TLS certificate
  context across Reddit and media connections.
- Stream video uploads from disk with python-telegram-bot 21.11.1 instead of
  buffering entire files. Limit complete video pipelines to two, copy audio
  during bounded ffmpeg muxes, and remove each sender's private temporary files.
- Bound metadata responses to 1 MiB and periodically collect dead job graphs
  and return unused native heap pages to the operating system.
- Add offline TLS and large-upload regression checks, application CI, and a
  whole-service resource recorder for the 500 MB normal / 1 GB spike targets.

## [1.0.0] - 2026-10-12

### Added

- Establish the first stable version of the existing Reddit-to-Telegram service.
- Require pull requests for every repository change, with an appropriate version
  bump, changelog entry, and release validation before merging.
- Add a release helper, a local guard against direct pushes to the default
  branch, and automatic GitHub releases from merged PRs.
- Include the recent live integration tests for actual Telegram delivery,
  Reddit supply, media processing, and resource cleanup on `@r_channels_test`.

### Fixed

- Include the recent fixes that close Telegram and Reddit HTTP clients, reuse
  the Telegram TLS certificate context, and bound media connection pools.
- Bound submitted jobs and simultaneous video uploads, drain work on shutdown,
  and limit native allocation arenas to reduce retained worker memory.

The recent application changes are recorded in commits
[69f4bdc](https://github.com/Fillll/reddit2telegram/commit/69f4bdc),
[1faf62e](https://github.com/Fillll/reddit2telegram/commit/1faf62e), and
[f4e8c34](https://github.com/Fillll/reddit2telegram/commit/f4e8c34).
