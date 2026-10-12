"""Prepare and validate stable SemVer releases using only the standard library."""

import argparse
from datetime import date, datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from zoneinfo import ZoneInfo

VERSION_RE = re.compile(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)')
HEADING_RE = re.compile(r'^## \[([^\]]+)\] - ([0-9]{4}-[0-9]{2}-[0-9]{2})$', re.MULTILINE)
LEVELS = ('major', 'minor', 'patch', 'bootstrap')


def parse_version(text):
    text = text.strip()
    if not VERSION_RE.fullmatch(text):
        raise ValueError(f'Expected a stable MAJOR.MINOR.PATCH version, got {text!r}')
    return tuple(int(part) for part in text.split('.'))


def next_version(previous, level):
    major, minor, patch = parse_version(previous)
    if level == 'major':
        result = major + 1, 0, 0
    elif level == 'minor':
        result = major, minor + 1, 0
    elif level == 'patch':
        result = major, minor, patch + 1
    else:
        raise ValueError('Use major, minor, or patch for an existing release')
    return '.'.join(str(part) for part in result)


def release_entries(changelog):
    entries = list(HEADING_RE.finditer(changelog))
    if not entries:
        raise ValueError('Changelog.md needs a dated release heading')
    versions = []
    for entry in entries:
        versions.append(parse_version(entry[1]))
        date.fromisoformat(entry[2])
    if versions != sorted(set(versions), reverse=True):
        raise ValueError('Changelog versions must be unique and newest first')
    return entries


def bump_from_body(body):
    matches = re.findall(r'^SemVer: (major|minor|patch|bootstrap)\s*$', body or '', re.MULTILINE)
    if len(matches) != 1:
        raise ValueError('PR body must contain exactly one SemVer: <level> line')
    return matches[0]


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root, text=True).strip()


def base_file(root, ref, filename):
    git(root, 'rev-parse', '--verify', '--end-of-options', ref)
    if not git(root, 'ls-tree', '--name-only', ref, '--', filename):
        return None
    # Preserve published changelog bytes, including final newlines.
    return subprocess.check_output(['git', 'show', f'{ref}:{filename}'], cwd=root, text=True)


def validate(root, base_ref, level):
    current = (root / 'VERSION').read_text().strip()
    parse_version(current)
    previous = base_file(root, base_ref, 'VERSION')
    expected = '1.0.0' if previous is None else next_version(previous, level)
    if previous is None and level != 'bootstrap':
        raise ValueError('The initial version requires SemVer: bootstrap')
    if current != expected:
        raise ValueError(f'{level} release must be {expected}, got {current}')
    changelog = (root / 'Changelog.md').read_text()
    entries = release_entries(changelog)
    if entries[0][1] != current:
        raise ValueError('The newest changelog entry must match VERSION')
    section = changelog[entries[0].end():entries[1].start() if len(entries) > 1 else None]
    if not re.search(r'^- \S', section, re.MULTILINE):
        raise ValueError('The new release needs at least one changelog bullet')
    old_changelog = base_file(root, base_ref, 'Changelog.md')
    if previous is not None and old_changelog is None:
        raise ValueError('The published base version is missing Changelog.md')
    if old_changelog is not None:
        old_entries = release_entries(old_changelog)
        if len(entries) < 2 or changelog[entries[1].start():] != old_changelog[old_entries[0].start():]:
            raise ValueError('Previously released changelog entries must be preserved')
    return current


def bump(root, level, summary, category, release_date):
    branch = git(root, 'branch', '--show-current')
    if not branch or branch in ('master', 'main'):
        raise ValueError('Create a topic branch before preparing a release')
    if not summary.strip() or '\n' in summary or '\r' in summary:
        raise ValueError('Use a nonempty, single-line changelog summary')
    date.fromisoformat(release_date)
    version = next_version((root / 'VERSION').read_text(), level)
    changelog = (root / 'Changelog.md').read_text()
    entries = release_entries(changelog)
    category = category or {'major': 'Changed', 'minor': 'Added', 'patch': 'Fixed'}[level]
    section = f'## [{version}] - {release_date}\n\n### {category}\n\n- {summary.strip()}\n\n'
    (root / 'VERSION').write_text(version + '\n')
    (root / 'Changelog.md').write_text(changelog[:entries[0].start()] + section + changelog[entries[0].start():])
    return version


def merged_pr_level(path, commit):
    prs = json.loads(path.read_text())
    matches = [pr for pr in prs if pr.get('merged_at') and
               pr.get('base', {}).get('ref') == 'master' and pr.get('merge_commit_sha') == commit]
    if len(matches) != 1:
        raise ValueError('Release commit must be introduced by one merged PR targeting master')
    return bump_from_body(matches[0].get('body'))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent.parent)
    commands = parser.add_subparsers(dest='command', required=True)
    prepare = commands.add_parser('bump')
    prepare.add_argument('level', choices=LEVELS[:3])
    prepare.add_argument('--summary', required=True)
    prepare.add_argument('--category', choices=('Added', 'Changed', 'Deprecated', 'Removed', 'Fixed', 'Security'))
    prepare.add_argument('--date', default=datetime.now(ZoneInfo('America/Los_Angeles')).date().isoformat())
    check = commands.add_parser('validate')
    check.add_argument('--base-ref', required=True)
    check.add_argument('--bump', choices=LEVELS)
    check.add_argument('--pr-json', type=Path)
    check.add_argument('--commit')
    commands.add_parser('notes')
    args = parser.parse_args(argv)
    try:
        if args.command == 'bump':
            print(bump(args.root, args.level, args.summary, args.category, args.date))
        elif args.command == 'validate':
            if args.pr_json:
                if not args.commit:
                    raise ValueError('--pr-json requires --commit')
                level = merged_pr_level(args.pr_json, args.commit)
            else:
                level = args.bump or bump_from_body(os.environ.get('PR_BODY'))
            print(validate(args.root, args.base_ref, level))
        else:
            changelog = (args.root / 'Changelog.md').read_text()
            entries = release_entries(changelog)
            if entries[0][1] != (args.root / 'VERSION').read_text().strip():
                raise ValueError('Release notes must match VERSION')
            print(changelog[entries[0].end():entries[1].start() if len(entries) > 1 else None].strip())
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'Release validation failed: {error}\n')


if __name__ == '__main__':
    main()
