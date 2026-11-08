"""Read-only health checks while a fresh live window elapses.

This tool never starts, stops, restarts or changes an application or collector.
An alert means inspect the same handles; a polling failure is not a terminal
measurement outcome. The original collector remains responsible for the cutoff.
"""

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import signal
import subprocess
import threading
import time


def service(unit, user=False):
    args = ['systemctl'] + (['--user'] if user else [])
    result = subprocess.run([*args, 'show', unit, '-p', 'LoadState', '-p', 'ActiveState',
                             '-p', 'MainPID', '-p', 'NRestarts'],
                            capture_output=True, text=True, timeout=10)
    value = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    value['query_returncode'] = result.returncode
    return value


def latest_timestamp(path):
    try:
        with path.open('rb') as stream:
            stream.seek(max(0, path.stat().st_size-32768))
            lines = stream.read().splitlines()
        # A writer can be appending the last line; retain the last complete row
        # rather than interpreting that transient read as a failed collector.
        for line in reversed(lines):
            try:
                value = json.loads(line)
                timestamp = value.get('ts')
                if isinstance(timestamp, (int, float)) and math.isfinite(timestamp):
                    return timestamp
            except (ValueError, AttributeError):
                continue
    except OSError:
        pass
    return None


def snapshot(directory, acknowledged_worker_pid=None):
    manifest = json.loads((directory / 'manifest.json').read_text())
    now = time.time()
    result = dict(checked_at=now, checked_utc=datetime.now(timezone.utc).isoformat(),
                  run_id=manifest['run_id'], label=manifest['label'],
                  status=manifest['status'], deadline=manifest['deadline'],
                  remaining_seconds=max(0, manifest['deadline']-now),
                  event='waiting', review_reasons=[], warnings=[])
    if manifest['status'] != 'running':
        result['event'] = 'finalized'
        return result
    worker = service('r2t_consumer_app.service')
    observers = {name: service(name, user=True) for name in
                 (f"r2tbench-{manifest['label']}.service", f"r2tbench-process-{manifest['label']}.service")}
    result.update(worker=worker, observers=observers, sample_ages_seconds={})
    worker_pid = int(worker.get('MainPID', '0'))
    expected_pid = acknowledged_worker_pid or manifest['runtime']['worker_pid']
    result['worker_pid_matches_initial'] = worker_pid == manifest['runtime']['worker_pid']
    if worker.get('ActiveState') != 'active' or worker_pid <= 0:
        result['review_reasons'].append('worker_service_unavailable')
    elif worker_pid != expected_pid:
        result['review_reasons'].append('worker_identity_changed')
    expected = Path(manifest['runtime']['worker_executable'])
    actual = Path('/proc') / str(worker_pid) / 'exe'
    result['worker_executable_matches_selected'] = worker_pid > 0 and actual.resolve() == expected.resolve()
    if not result['worker_executable_matches_selected']:
        result['review_reasons'].append('worker_executable_changed_or_unreadable')
    for name, observer in observers.items():
        if observer.get('ActiveState') != 'active' or int(observer.get('MainPID', '0')) <= 0:
            result['review_reasons'].append('observer_service_unavailable:'+name)
        if int(observer.get('NRestarts', '0')) > 0:
            result['warnings'].append('observer_has_restarts:'+name)
    for name in ('samples.jsonl', 'processes.jsonl'):
        observed = latest_timestamp(directory / name)
        age = max(0, now-observed) if observed is not None else None
        result['sample_ages_seconds'][name] = age
        if (age is not None and age > 120) or (age is None and now-manifest['started_at'] > 120):
            result['review_reasons'].append('observations_stale_or_missing:'+name)
    if result['review_reasons']:
        result['event'] = 'review_required'
    return result


def watch(directory, minutes, acknowledged_worker_pid=None):
    stop = threading.Event()
    for which in (signal.SIGTERM, signal.SIGINT):
        signal.signal(which, lambda *_: stop.set())
    deadline = time.monotonic()+minutes*60
    while not stop.is_set():
        try:
            result = snapshot(directory, acknowledged_worker_pid)
        except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
            result = dict(event='review_required', error_type=type(error).__name__,
                          detail='Read failed; inspect the same handles without restarting them.')
        print(json.dumps(result, separators=(',', ':')), flush=True)
        if result['event'] != 'waiting':
            return 0 if result['event'] == 'finalized' else 2
        remaining = deadline-time.monotonic()
        if remaining <= 0:
            print(json.dumps(dict(event='verified_wait_checkpoint', state=result)), flush=True)
            return 0
        stop.wait(min(60, remaining))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--minutes', type=float, default=60)
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--acknowledged-worker-pid', type=int,
                        help='Use only after reviewing and recording an actual worker restart')
    args = parser.parse_args()
    if args.once:
        print(json.dumps(snapshot(args.directory.resolve(), args.acknowledged_worker_pid), indent=2))
    else:
        if not math.isfinite(args.minutes) or args.minutes <= 0:
            parser.error('--minutes must be positive and finite')
        raise SystemExit(watch(args.directory.resolve(), args.minutes, args.acknowledged_worker_pid))


if __name__ == '__main__':
    main()
