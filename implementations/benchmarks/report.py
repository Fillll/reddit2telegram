"""Produce the requested single-image report from finalized fresh live windows."""

import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path

from report_data import analyze_experiment, require_final


def atomic_write(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f'.{os.getpid()}.tmp')
    temporary.write_bytes(raw)
    temporary.replace(path)


def csv_bytes(rows, names):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=names)
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def distributions(value, path=''):
    if not isinstance(value, dict):
        return
    if {'count', 'average', 'median', 'p95', 'maximum', 'minimum'} <= value.keys():
        yield path, value
    else:
        for key, item in value.items():
            if key not in ('modules', 'source_receipts', 'build'):
                yield from distributions(item, f'{path}.{key}' if path else key)


def export(bundle, output):
    require_final(bundle)
    # Lazy import: inspecting active evidence needs no plotting dependencies.
    from render_report import render
    output.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(bundle, indent=2, sort_keys=True, allow_nan=False)+'\n').encode()
    figure = output / 'r2t-live-comparison.png'
    render_receipt = render(bundle, figure)
    atomic_write(output / 'comparison.json', raw)
    rows = []
    for run in bundle['runs']:
        for metric, values in distributions(run):
            rows.append(dict(label=run['label'], metric=metric, **values))
    atomic_write(output / 'distributions.csv', csv_bytes(rows,
        ['label', 'metric', 'count', 'average', 'median', 'p95', 'maximum', 'minimum']))
    overview = []
    for run in bundle['runs']:
        jobs = run['jobs']
        overview.append(dict(label=run['label'], status=run['status'],
            started_utc=run['started_iso'], ended_utc=run['ended_iso'],
            exposure_hours=run['exposure_seconds']/3600,
            sample_coverage_fraction=run['sampling_coverage_fraction'],
            process_coverage_fraction=run['processes']['coverage_fraction'],
            completed_jobs=jobs['completed'], successful_jobs=jobs['successful'], failed_jobs=jobs['failed'],
            telegram_messages=jobs['counters'].get('telegram_messages'),
            application_cpu_seconds=run['components']['application']['cpu']['seconds'],
            cpu_seconds_per_completed_job=run['cpu_seconds_per_completed_job'],
            cpu_seconds_per_successful_job=run['cpu_seconds_per_successful_job']))
    atomic_write(output / 'windows.csv', csv_bytes(overview, list(overview[0])))
    counters = [dict(label=run['label'], counter=key, value=value)
                for run in bundle['runs'] for key, value in sorted(run['jobs']['counters'].items())]
    atomic_write(output / 'counters.csv', csv_bytes(counters, ['label', 'counter', 'value']))
    render_receipt.update(comparison_sha256=hashlib.sha256(raw).hexdigest(),
                          image_sha256=hashlib.sha256(figure.read_bytes()).hexdigest())
    atomic_write(output / 'render-receipt.json',
                 (json.dumps(render_receipt, indent=2, sort_keys=True)+'\n').encode())
    return figure


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--runs', type=Path, help='Original ignored runs directory with its adjacent ledger')
    source.add_argument('--bundle', type=Path, help='Previously reviewed portable comparison.json')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--inspect', action='store_true', help='Show evidence readiness without writing a report')
    args = parser.parse_args()
    bundle = analyze_experiment(args.runs.resolve()) if args.runs else json.loads(args.bundle.read_text())
    if args.inspect:
        print(json.dumps(dict(final_ready=bundle['final_ready'], missing=bundle['missing_labels'],
            unfinished=bundle['unfinished_labels'], overlaps=bundle['overlapping_windows'],
            runs=[dict(label=r['label'], status=r['status'], samples=r['sample_count'],
                       completed_jobs=r['jobs']['completed'], paired_jobs=r['jobs']['paired_executions'],
                       process_samples=r['processes']['samples']) for r in bundle['runs']]), indent=2))
        return
    require_final(bundle)
    if args.output is None:
        parser.error('--output is required for a final report')
    print(export(bundle, args.output.resolve()))


if __name__ == '__main__':
    main()
