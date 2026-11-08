"""Ledger safety checks; no application traffic or simulated performance data."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


path = Path(__file__).resolve().parents[1] / 'implementations/benchmarks/runner.py'
spec = importlib.util.spec_from_file_location('benchmark_campaign_runner', path)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class CampaignLedgerSafety(unittest.TestCase):
    def test_campaign_cannot_escape_private_state(self):
        root = Path('/project')
        for name in ('', '../escape', '/tmp/escape', 'UPPER', 'a'*41):
            with self.subTest(name=name), self.assertRaises(ValueError):
                runner.campaign_base(root, name)
        self.assertEqual(runner.campaign_base(root, 'go-http1'),
                         runner.bench(root) / 'state/campaigns/go-http1')

    def test_finished_original_is_preserved_and_cannot_be_repeated_in_place(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shared = runner.bench(root) / 'state'
            original = shared / 'experiment.json'
            runner.atomic_json(original, {'runs': {'go': {'run_id': 'original-go', 'status': 'finished'}}})
            before = original.read_bytes()
            with self.assertRaises(ValueError):
                runner.check_launch_available(root, shared, 'go')
            followup = runner.campaign_base(root, 'go-http1') / 'state'
            self.assertEqual(runner.check_launch_available(root, followup, 'go'), {'runs': {}})
            self.assertEqual(original.read_bytes(), before)

    def test_expired_but_unfinalized_collector_blocks_new_campaign(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shared = runner.bench(root) / 'state'
            runner.atomic_json(shared / 'active.json', {'status': 'running', 'deadline': 0})
            with self.assertRaises(ValueError):
                runner.check_launch_available(root, runner.campaign_base(root, 'go-http1') / 'state', 'go')

    def test_running_original_or_used_campaign_label_blocks_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shared = runner.bench(root) / 'state'
            followup = runner.campaign_base(root, 'go-http1') / 'state'
            runner.atomic_json(shared / 'experiment.json', {'runs': {'go': {'status': 'running'}}})
            with self.assertRaises(ValueError):
                runner.check_launch_available(root, followup, 'go')
            runner.atomic_json(shared / 'experiment.json', {'runs': {'go': {'status': 'finished'}}})
            runner.atomic_json(followup / 'experiment.json', {'runs': {'go': {'status': 'finished'}}})
            with self.assertRaises(ValueError):
                runner.check_launch_available(root, followup, 'go')

    def test_another_unfinalized_campaign_blocks_even_without_event_pointer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            other = runner.campaign_base(root, 'other') / 'state'
            runner.atomic_json(other / 'experiment.json', {'runs': {'go': {'status': 'running'}}})
            with self.assertRaises(ValueError):
                runner.check_launch_available(root, runner.campaign_base(root, 'go-http1') / 'state', 'go')

    def test_corrupt_original_ledger_is_not_treated_as_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shared = runner.bench(root) / 'state'
            shared.mkdir(parents=True)
            path = shared / 'experiment.json'
            path.write_text('{incomplete')
            with self.assertRaises(ValueError):
                runner.check_launch_available(root, runner.campaign_base(root, 'go-http1') / 'state', 'go')
            self.assertEqual(path.read_text(), '{incomplete')


if __name__ == '__main__':
    unittest.main()
