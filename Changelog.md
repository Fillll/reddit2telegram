# Changelog

All notable changes are recorded here, newest release first. Versions follow
[Semantic Versioning](https://semver.org/). Dates use America/Los_Angeles.
The history before this initial versioned snapshot remains in Git.

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
