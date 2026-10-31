"""Protect the main-run cutoff and the requested descending tail."""
import collections
import csv
from pathlib import Path
import unittest

from croniter import croniter


SCHEDULE = Path(__file__).resolve().parents[1] / 'reddit2telegram' / 'own.cron'


def main_runs():
    runs = {}
    with SCHEDULE.open() as source:
        for row in csv.DictReader(source, delimiter='\t'):
            name = row['submodule_name']
            if name.startswith('tech_') or name in runs:
                continue
            minutes = croniter.expand(row['MASK'])[0][0]
            runs[name] = 0 if minutes == ['*'] else min(minutes)
    return runs


class MainRunScheduleTests(unittest.TestCase):
    def test_no_main_runs_after_minute_45(self):
        late = {name: minute for name, minute in main_runs().items() if minute > 45}
        self.assertEqual(late, {})

    def test_descending_main_run_tail(self):
        counts = collections.Counter(main_runs().values())
        for minute in range(17, 46):
            with self.subTest(minute=minute):
                self.assertEqual(counts[minute], 46 - minute)


if __name__ == '__main__':
    unittest.main()
