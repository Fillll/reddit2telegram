# Repository working rules

## Pull requests

- Make every repository change on a topic branch and through a GitHub PR,
  including documentation, tests, dependency updates, and channel configuration.
- Never push commits directly to `master` or `main`, including emergency fixes.
- Install the repository's local push guard with
  `git config core.hooksPath scripts/hooks` before pushing.
- The maintainer authorizes agents to merge their own PRs after reviewing the
  complete diff and passing the relevant tests and release checks. Do not ask
  for merge permission again within that scope.
- Before merging, fetch the latest base branch, refresh the release bump if
  another PR has released in the meantime, and confirm the checked PR head.
- Use a squash or merge commit so the release workflow can validate the
  complete PR against the previous default-branch commit.
- Preserve unrelated local changes. Use an isolated worktree when the current
  checkout has uncommitted work; never bundle those edits without authorization.
- After merging, update checkouts by fast-forwarding. Publish releases through
  the release workflow; never move an existing version tag.

## Versions and changelog

- `VERSION` is the single source of truth. Use stable `MAJOR.MINOR.PATCH` values.
- Choose the version bump autonomously from the final PR scope:
  - **Major:** incompatible changes to documented CLI/configuration, persisted
    MongoDB formats requiring migration, or established posting behavior.
  - **Minor:** new compatible features, optional configuration, new channels,
    or deprecation of a public interface.
  - **Patch:** compatible fixes, resource/performance repairs, and maintenance
    releases containing only documentation, tests, build, or internal changes.
- Make exactly one release increment per PR, relative to the latest base
  version. Additional commits within the PR update its notes, not its version.
- Update `Changelog.md` in the same PR. Explain user/operator-visible behavior
  and migrations; preserve every existing release entry.
- Include one plain `SemVer: major`, `SemVer: minor`, or `SemVer: patch` line in
  the PR body. `SemVer: bootstrap` is reserved for the initial 1.0.0 PR.
- Use `python3 scripts/release.py bump <level> --summary '...'` on a fresh
  topic branch, then validate against `origin/master` with
  `python3 scripts/release.py validate --base-ref origin/master --bump <level>`
  before pushing. Explain the bump in the PR description.

## Validation

- Run release checks with `python3 -m unittest discover -s tests -p test_release.py`.
- Run application tests appropriate to the change. Live tests are opt-in, send
  real messages only to `@r_channels_test`, and require local credentials.
- Do not put production credentials, runtime logs, or generated media into Git
  or ordinary GitHub Actions runs. Never expose bot tokens in logs.
