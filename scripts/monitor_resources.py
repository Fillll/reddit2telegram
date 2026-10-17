"""Record whole-service memory peaks and connection counts without credentials."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time


CGROUP = Path('/sys/fs/cgroup/system.slice/r2t_consumer_app.service')
NORMAL_TARGET = 500_000_000
SPIKE_TARGET = 1_000_000_000


def snapshot():
    record = {'ts': datetime.now(timezone.utc).isoformat()}
    pids = (CGROUP / 'cgroup.procs').read_text().split()
    processes = []
    for value in pids:
        try:
            name = (Path('/proc') / value / 'comm').read_text().strip()
            processes.append({'pid': int(value), 'name': name})
        except FileNotFoundError:
            pass
    main = next((p['pid'] for p in processes if p['name'].startswith('python')), None)
    record.update(processes=processes, pid=main,
                  service_bytes=int((CGROUP / 'memory.current').read_text()),
                  service_peak_bytes=int((CGROUP / 'memory.peak').read_text()))
    if main is None:
        record['status'] = 'no_python_process'
        return record
    proc = Path('/proc') / str(main)
    status = dict(line.split(':', 1) for line in (proc / 'status').read_text().splitlines() if ':' in line)
    record.update(status='running', rss_bytes=int(status['VmRSS'].split()[0]) * 1024,
                  rss_peak_bytes=int(status['VmHWM'].split()[0]) * 1024,
                  threads=int(status['Threads']))
    fds = list((proc / 'fd').iterdir())
    inodes = set()
    for fd in fds:
        try:
            match = re.fullmatch(r'socket:\[(\d+)\]', str(fd.readlink()))
            if match:
                inodes.add(match[1])
        except OSError:
            pass
    states = Counter()
    for filename in ('tcp', 'tcp6'):
        for line in (proc / 'net' / filename).read_text().splitlines()[1:]:
            row = line.split()
            if row[9] in inodes:
                states[row[3]] += 1
    cpu = dict(line.split() for line in (CGROUP / 'cpu.stat').read_text().splitlines())
    record.update(fds=len(fds), close_wait=states['08'], established=states['01'],
                  cpu_usage_usec=int(cpu['usage_usec']),
                  service_under_normal_target=record['service_bytes'] < NORMAL_TARGET,
                  service_peak_under_spike_target=record['service_peak_bytes'] < SPIKE_TARGET)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--log', type=Path, required=True)
    parser.add_argument('--seconds', type=int, default=0, help='0 takes one snapshot (suitable for cron)')
    parser.add_argument('--interval', type=float, default=5)
    args = parser.parse_args()
    if args.interval <= 0 or args.seconds < 0:
        parser.error('Use a positive interval and nonnegative duration')
    args.log.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + args.seconds
    last_notice = 0
    while True:
        try:
            record = snapshot()
        except (OSError, ValueError, KeyError) as error:
            record = {'ts': datetime.now(timezone.utc).isoformat(), 'status': type(error).__name__}
        with args.log.open('a') as output:
            output.write(json.dumps(record, sort_keys=True) + '\n')
        now = time.monotonic()
        if now - last_notice >= 60 or not args.seconds:
            print(json.dumps(record, sort_keys=True), flush=True)
            last_notice = now
        if now >= deadline:
            return
        time.sleep(min(args.interval, deadline - now))


if __name__ == '__main__':
    main()
