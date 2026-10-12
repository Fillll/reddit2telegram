"""Release policy integration tests; no application credentials or dependencies."""

import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location('release', REPO / 'scripts/release.py')
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.git('init', '-b', 'topic')
        self.git('config', 'user.email', 'release@example.invalid')
        self.git('config', 'user.name', 'Release tests')
        self.old_notes = '# Changelog\n\n## [1.2.3] - 2026-10-01\n\n### Fixed\n\n- Published fix.\n'
        (self.root / 'VERSION').write_text('1.2.3\n')
        (self.root / 'Changelog.md').write_text(self.old_notes)
        self.commit()
        self.base = self.git('rev-parse', 'HEAD')

    def git(self, *args):
        return release.git(self.root, *args)

    def commit(self):
        self.git('add', '.')
        self.git('commit', '-qm', 'Base release')

    def prepare(self, level='patch'):
        return release.bump(self.root, level, 'A useful change.', None, '2026-10-12')

    def test_bumps_reset_lower_components_and_preserve_history(self):
        for level, expected in [('patch', '1.2.4'), ('minor', '1.3.0'), ('major', '2.0.0')]:
            with self.subTest(level=level):
                (self.root / 'VERSION').write_text('1.2.3\n')
                (self.root / 'Changelog.md').write_text(self.old_notes)
                self.assertEqual(self.prepare(level), expected)
                self.assertEqual(release.validate(self.root, self.base, level), expected)
                self.assertTrue((self.root / 'Changelog.md').read_text().endswith(self.old_notes.split('\n\n', 1)[1]))

    def test_stable_versions_reject_ambiguous_or_prerelease_values(self):
        for value in ['v1.0.0', '01.0.0', '1.0', '1.0.0-beta', '1.0.0+build', '-1.0.0']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                release.parse_version(value)

    def test_wrong_bump_is_rejected(self):
        self.prepare()
        with self.assertRaisesRegex(ValueError, 'must be 1.3.0'):
            release.validate(self.root, self.base, 'minor')

    def test_version_and_latest_notes_must_agree(self):
        self.prepare()
        (self.root / 'VERSION').write_text('1.2.5\n')
        with self.assertRaises(ValueError):
            release.validate(self.root, self.base, 'patch')
        (self.root / 'VERSION').write_text('1.2.4\n')
        notes = (self.root / 'Changelog.md').read_text().replace('[1.2.4]', '[1.2.5]')
        (self.root / 'Changelog.md').write_text(notes)
        with self.assertRaisesRegex(ValueError, 'match VERSION'):
            release.validate(self.root, self.base, 'patch')

    def test_release_requires_notes_and_preserves_published_notes(self):
        self.prepare()
        good = (self.root / 'Changelog.md').read_text()
        cases = [good.replace('- A useful change.', ''),
                 good.replace('Published fix.', 'Rewritten history.'),
                 good[:good.index('## [1.2.3]')]]
        for notes in cases:
            with self.subTest(notes=notes), self.assertRaises(ValueError):
                (self.root / 'Changelog.md').write_text(notes)
                release.validate(self.root, self.base, 'patch')

    def test_duplicate_versions_and_invalid_dates_are_rejected(self):
        for notes in [self.old_notes + self.old_notes, self.old_notes.replace('2026-10-01', '2026-02-30')]:
            with self.assertRaises(ValueError):
                release.release_entries(notes)

    def test_bootstrap_requires_initial_version_and_explicit_marker(self):
        self.git('rm', 'VERSION', 'Changelog.md')
        self.commit()
        base = self.git('rev-parse', 'HEAD')
        (self.root / 'VERSION').write_text('1.0.0\n')
        (self.root / 'Changelog.md').write_text('## [1.0.0] - 2026-10-12\n\n- Initial release.\n')
        self.assertEqual(release.validate(self.root, base, 'bootstrap'), '1.0.0')
        with self.assertRaises(ValueError):
            release.validate(self.root, base, 'patch')
        (self.root / 'VERSION').write_text('0.1.0\n')
        with self.assertRaises(ValueError):
            release.validate(self.root, base, 'bootstrap')

    def test_bump_refuses_default_branch_and_invalid_summary(self):
        for summary in ['', 'Two\nlines']:
            with self.assertRaises(ValueError):
                release.bump(self.root, 'patch', summary, None, '2026-10-12')
        self.git('checkout', '-b', 'master')
        with self.assertRaisesRegex(ValueError, 'topic branch'):
            self.prepare()

    def test_pr_body_requires_one_literal_marker(self):
        self.assertEqual(release.bump_from_body('Summary\n\nSemVer: minor\n\nTests passed.'), 'minor')
        for body in ['', 'SemVer: tiny', 'SemVer: patch\nSemVer: major', '`SemVer: patch`']:
            with self.subTest(body=body), self.assertRaises(ValueError):
                release.bump_from_body(body)

    def test_publisher_accepts_only_exact_merged_pr_commit(self):
        path = self.root / 'prs.json'
        valid = {'merged_at': '2026-10-12T00:00:00Z', 'base': {'ref': 'master'},
                 'merge_commit_sha': 'abc123', 'body': 'SemVer: minor'}
        path.write_text(json.dumps([valid]))
        self.assertEqual(release.merged_pr_level(path, 'abc123'), 'minor')
        for prs in [[], [dict(valid, merged_at=None)], [dict(valid, merge_commit_sha='different')],
                    [dict(valid, base={'ref': 'topic'})], [valid, valid]]:
            with self.subTest(prs=prs), self.assertRaises(ValueError):
                path.write_text(json.dumps(prs))
                release.merged_pr_level(path, 'abc123')

    def test_push_guard_blocks_default_branches_and_allows_topics(self):
        hook = REPO / 'scripts/hooks/pre-push'
        for branch, expected in [('master', 1), ('main', 1), ('topic', 0)]:
            result = subprocess.run([str(hook)], input=f'refs/heads/topic abc refs/heads/{branch} def\n',
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, expected)

    def test_cli_notes_extracts_only_current_release(self):
        self.prepare()
        result = subprocess.run(['python3', str(REPO / 'scripts/release.py'), '--root', str(self.root), 'notes'],
                                text=True, capture_output=True, check=True)
        self.assertIn('A useful change.', result.stdout)
        self.assertNotIn('Published fix.', result.stdout)


if __name__ == '__main__':
    unittest.main()
