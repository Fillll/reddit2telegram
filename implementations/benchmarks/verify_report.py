"""Independently reconcile report metrics against a frozen copy of fresh live inputs.

This does not launch application work or generate benchmark input. The private
copy only prevents a collector append from changing inputs during arithmetic
checks. No copied raw rows are exported or retained after the check.
"""

import argparse
from collections import Counter
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import shutil
import tempfile

from report_data import analyze_experiment, require_final, EvidenceError


def close(actual, expected):
    if expected is None:
        assert actual is None, (actual, expected)
    else:
        assert math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-8), (actual, expected)


def reference_stats(values):
    ordered = sorted(v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v))
    if not ordered:
        return dict(count=0, average=None, median=None, p95=None, maximum=None, minimum=None)
    n = len(ordered)
    total = sum((Decimal(str(v)) for v in ordered), Decimal(0))
    median = ordered[n//2] if n % 2 else (ordered[n//2-1]+ordered[n//2])/2
    return dict(count=n, average=float(total/Decimal(n)), median=median,
                p95=ordered[(n*95+99)//100-1], maximum=ordered[-1], minimum=ordered[0])


def check_stats(actual, reference):
    assert actual['count'] == reference['count']
    for key in ('average', 'median', 'p95', 'maximum', 'minimum'):
        close(actual[key], reference[key])


def records(path):
    if not path.exists():
        return []
    values = []
    for line in path.read_bytes().splitlines():
        try:
            value = json.loads(line)
            if isinstance(value, dict):
                values.append(value)
        except (ValueError, UnicodeError):
            continue
    return values


def verify(runs):
    with tempfile.TemporaryDirectory(prefix='r2t-report-check-') as temporary:
        root = Path(temporary)
        (root / 'state').mkdir()
        (root / 'runs').mkdir()
        shutil.copyfile(runs.parent / 'state/experiment.json', root / 'state/experiment.json')
        for manifest in runs.glob('*/manifest.json'):
            destination = root / 'runs' / manifest.parent.name
            destination.mkdir()
            shutil.copyfile(manifest, destination / 'manifest.json')
            for filename in ('samples.jsonl', 'events.jsonl', 'queue.jsonl', 'notes.jsonl',
                             'processes.jsonl', 'sampling_errors.jsonl', 'process_sampling_errors.jsonl'):
                path = manifest.parent / filename
                if path.exists():
                    shutil.copyfile(path, destination / filename)
        bundle = analyze_experiment(root / 'runs')
        results = []
        for model in bundle['runs']:
            directory = root / 'runs' / model['run_id']
            start, end = model['started_at'], model['effective_end']
            samples = [r for r in records(directory / 'samples.jsonl')
                       if 'components' in r and start <= r.get('ts', -1) <= end]
            assert len(samples) == model['sample_count']
            memory = [sum(s['components'][n]['memory_bytes'] for n in ('worker', 'scheduler'))
                      for s in samples if all(s['components'].get(n) is not None for n in ('worker', 'scheduler'))]
            check_stats(model['components']['application']['memory_bytes'], reference_stats(memory))
            cpu_total, short_cpu, short_seconds = Decimal(0), Decimal(0), Decimal(0)
            rates = []
            intervals = 0
            for left, right in zip(samples, samples[1:]):
                names = ('worker', 'scheduler')
                if right['ts'] <= left['ts'] or any(left['components'].get(n) is None or right['components'].get(n) is None for n in names):
                    continue
                changes = [right['components'][n]['cpu_usec']-left['components'][n]['cpu_usec'] for n in names]
                if min(changes) < 0:
                    continue
                amount = Decimal(sum(changes))/Decimal(1_000_000)
                cpu_total += amount
                intervals += 1
                dt = Decimal(str(right['ts']-left['ts']))
                if dt <= 10:
                    short_cpu += amount
                    short_seconds += dt
                    rates.append(float(amount/dt*100))
            close(model['components']['application']['cpu']['seconds'], float(cpu_total) if intervals else None)
            cpu_reference = reference_stats(rates)
            cpu_reference['average'] = float(short_cpu/short_seconds*100) if short_seconds else None
            check_stats(model['components']['application']['cpu']['sampled_percent_one_core'], cpu_reference)
            events = [r for r in records(directory / 'events.jsonl')
                      if start <= r.get('ts', -1) < end and r.get('run_id') == model['run_id']]
            ends = [r for r in events if r.get('event') == 'job_end']
            beginnings = [r for r in events if r.get('event') == 'job_start']
            if (directory / 'events.jsonl').exists():
                assert len(ends) == model['jobs']['completed']
                assert sum(r.get('status') == 'success' for r in ends) == model['jobs']['successful']
                assert model['jobs']['failed'] + model['jobs']['successful'] == len(ends)
                for metric in ('http_response_body_bytes', 'telegram_request_body_bytes', 'telegram_messages'):
                    expected = sum(r.get('counters', {}).get(metric, 0) for r in ends)
                    close(model['jobs']['counters'].get(metric, 0), expected)
                close(model['cpu_seconds_per_completed_job'],
                      float(cpu_total)/len(ends) if intervals and ends else None)
            start_counts = Counter(r.get('task_id') for r in beginnings)
            end_counts = Counter(r.get('task_id') for r in ends)
            event_data_present = (directory / 'events.jsonl').exists()
            full_unique_pairing = event_data_present and all(count == 1 for count in [*start_counts.values(), *end_counts.values()])
            if full_unique_pairing:
                starts_by_id = {r['task_id']: r for r in beginnings}
                eligible = [r for r in ends if r.get('task_id') in starts_by_id
                            and starts_by_id[r['task_id']].get('module') == r.get('module')]
                assert len(eligible) == model['jobs']['paired_executions']
                check_stats(model['jobs']['processing_seconds'], reference_stats([r.get('duration_seconds') for r in eligible]))
                check_stats(model['jobs']['queue_wait_seconds'], reference_stats([r.get('queue_wait_seconds') for r in eligible]))
            queues = [r for r in records(directory / 'queue.jsonl') if start <= r.get('ts', -1) <= end]
            backlog = [r['counts']['1']+r['counts']['5'] for r in queues if '1' in r.get('counts', {}) and '5' in r['counts']]
            check_stats(model['queued_backlog'], reference_stats(backlog))
            assert all(value['scope'] == 'cgroup_lifetime' for value in model['kernel_peaks'].values())
            assert all(start <= r['ts'] <= end for r in samples)
            for filename, receipt in model['source_receipts'].items():
                if receipt['present']:
                    assert hashlib.sha256((directory / filename).read_bytes()).hexdigest() == receipt['sha256']
            results.append(dict(label=model['label'], samples=len(samples), completed_jobs=len(ends),
                checked=['memory mean/median/P95/min/max', 'CPU cumulative/weighted mean/median/P95',
                         'job outcomes/body counters/CPU per completed job', 'queue backlog',
                         'window boundaries/source hashes/kernel-peak scope'],
                unique_execution_timing_verified=full_unique_pairing,
                timing_limit=None if full_unique_pairing else (
                    'Repeated task IDs need an additional execution-pairing review' if event_data_present else 'Event data is unavailable'),
                source_receipts=model['source_receipts']))
        refusal_verified = None
        if not bundle['final_ready']:
            try:
                require_final(bundle)
            except EvidenceError:
                refusal_verified = True
            else:
                raise AssertionError('An unfinished experiment was accepted as a final report')
        return dict(scope='Arithmetic reconciliation against a private frozen copy of fresh live observations; no app requests or replay',
                    final_ready=bundle['final_ready'], unfinished_final_refusal_verified=refusal_verified,
                    runs=results, rendered_image_verified=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=Path, required=True)
    parser.add_argument('--receipt', type=Path)
    args = parser.parse_args()
    result = verify(args.runs.resolve())
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(dict(final_ready=result['final_ready'],
        runs=[{key: row[key] for key in ('label', 'samples', 'completed_jobs', 'unique_execution_timing_verified')}
              for row in result['runs']],
        unfinished_final_refusal_verified=result['unfinished_final_refusal_verified']), indent=2))


if __name__ == '__main__':
    main()
