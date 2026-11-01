"""Supplement live cgroup samples with read-only process roles; never run app work.

RSS can be separated for observed worker/ffmpeg/helper processes. Parent reaped
child CPU plus live children accounts for short helpers between polls, but that
CPU cannot be attributed specifically to ffmpeg versus other helpers. Preserve
that distinction rather than implying five-second polling captures every child.
"""

import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import threading
import time

import psutil


def append(path, value):
    data = (json.dumps(value, separators=(',', ':')) + '\n').encode()
    fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600)
    try:
        if os.write(fd, data) != len(data):
            raise OSError('Incomplete measurement write')
    finally:
        os.close(fd)


def snapshot(group):
    paths = [group / 'cgroup.procs', *group.rglob('*/cgroup.procs')]
    pids = {int(pid) for path in paths for pid in path.read_text().split()}
    processes, unreadable = [], 0
    for pid in sorted(pids):
        try:
            process = psutil.Process(pid)
            with process.oneshot():
                name, parent = process.name(), process.ppid()
                times = process.cpu_times()
                role = ('ffmpeg' if name == 'ffmpeg' else
                        'worker' if parent not in pids else 'other_helper')
                processes.append(dict(pid=pid, created_at=process.create_time(),
                    name=name, role=role, parent=parent,
                    cpu_seconds=times.user + times.system,
                    reaped_child_cpu_seconds=times.children_user + times.children_system,
                    rss_bytes=process.memory_info().rss, fds=process.num_fds(),
                    threads=process.num_threads()))
        except (psutil.NoSuchProcess, psutil.AccessDenied, ProcessLookupError):
            unreadable += 1
    roles = {name: dict(processes=0, rss_bytes=0, fds=0, threads=0)
             for name in ('worker', 'ffmpeg', 'other_helper')}
    for process in processes:
        role = roles[process['role']]
        role['processes'] += 1
        for key in ('rss_bytes', 'fds', 'threads'):
            role[key] += process[key]
    # Each root's waited child times include all reaped descendant work. Live
    # descendants supply the un-reaped portion; do not add descendants' own
    # child times again, which would count reaped grandchildren twice.
    roots = [p for p in processes if p['role'] == 'worker']
    helpers = [p for p in processes if p['role'] != 'worker']
    return dict(processes=processes, roles=roles, unreadable_processes=unreadable,
                worker_cpu_seconds=sum(p['cpu_seconds'] for p in roots),
                helpers_cpu_seconds=sum(p['reaped_child_cpu_seconds'] for p in roots)
                                    + sum(p['cpu_seconds'] for p in helpers),
                worker_identities=[[p['pid'], p['created_at']] for p in roots])


def collect(directory, interval=5):
    directory = directory.resolve()
    lock = (directory / 'process_sampler.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise ValueError('A process sampler is already running for this window')
    manifest = json.loads((directory / 'manifest.json').read_text())
    if manifest['deadline'] - manifest['started_at'] != 86400:
        raise ValueError('Expected the original 24-hour window')
    if time.time() >= manifest['deadline']:
        return  # A delayed service restart must not collect beyond the deadline.
    stop = threading.Event()
    for which in (signal.SIGTERM, signal.SIGINT):
        signal.signal(which, lambda *_: stop.set())
    started, count, errors = time.time(), 0, 0
    append(directory / 'notes.jsonl', dict(ts=started, event='process_sampler_started',
        run_id=manifest['run_id'], delay_from_window_start_seconds=started-manifest['started_at'],
        detail='Read-only supplementary worker/ffmpeg/helper RSS and CPU observations; '
               'earlier process-role measurements are unavailable; no app, schedule or deadline change.'))
    next_sample = time.monotonic()
    while not stop.is_set() and time.time() < manifest['deadline']:
        observed_at = time.time()
        if observed_at >= manifest['started_at']:
            try:
                row = snapshot(Path(manifest['cgroups']['worker']))
                row.update(ts=observed_at, schema=1, run_id=manifest['run_id'])
                if time.time() < manifest['deadline']:
                    append(directory / 'processes.jsonl', row)
                    count += 1
            except (OSError, ValueError, psutil.Error) as error:
                errors += 1
                append(directory / 'process_sampling_errors.jsonl',
                       dict(ts=observed_at, error_type=type(error).__name__))
        next_sample += interval
        stop.wait(max(0, min(next_sample-time.monotonic(), manifest['deadline']-time.time())))
    append(directory / 'notes.jsonl', dict(ts=time.time(), event='process_sampler_finished',
        run_id=manifest['run_id'], samples=count, sampling_errors=errors,
        stopped_before_deadline=stop.is_set(), original_deadline=manifest['deadline']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    collect(args.directory)


if __name__ == '__main__':
    main()
