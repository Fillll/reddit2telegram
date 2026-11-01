"""Persistent, live-only 24-hour measurement runner (no application test traffic)."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import signal
import statistics
import subprocess
import sys
import time
import uuid


DURATION = 24 * 60 * 60
INTERVAL = 5
LABELS = ('python312', 'python315', 'rust', 'swift', 'cpp', 'c', 'go')


def stamp():
    return datetime.now(timezone.utc).isoformat()


def read_json(path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_name(path.name + '.' + str(os.getpid()) + '.tmp')
    with temp.open('w') as stream:
        os.chmod(temp, 0o600)
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(path)


def append(path, value):
    with path.open('a') as stream:
        stream.write(json.dumps(value, separators=(',', ':')) + '\n')


def command(args, cwd=None):
    return subprocess.check_output(args, cwd=cwd, text=True).strip()


def bench(root):
    return root / 'implementations/benchmarks'


def fingerprint(root):
    names = command(['git', 'ls-files', '-z'], root).split('\0')
    source = hashlib.sha256()
    for name in sorted(n for n in names if n):
        path = root / name
        if path.is_file():
            source.update(name.encode() + b'\0' + path.read_bytes() + b'\0')
    paths = [root / 'reddit2telegram/configs/prod.yml', root / 'reddit2telegram/own.cron']
    return dict(commit=command(['git', 'rev-parse', 'HEAD'], root),
                tracked_source_sha256=source.hexdigest(),
                dirty_diff_sha256=hashlib.sha256(subprocess.check_output(['git', 'diff', 'HEAD'], cwd=root)).hexdigest(),
                configuration_sha256={str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                                      for p in paths if p.exists()})


def cgroup_stats(path):
    if not path.exists():
        return None
    try:
        cpu = dict(line.split() for line in (path / 'cpu.stat').read_text().splitlines())
        memory = dict(line.split() for line in (path / 'memory.stat').read_text().splitlines())
        return dict(cpu_usec=int(cpu['usage_usec']),
                    memory_bytes=int((path / 'memory.current').read_text()),
                    kernel_peak_bytes=int((path / 'memory.peak').read_text()),
                    file_cache_bytes=int(memory.get('file', 0)),
                    pids=sorted({int(p) for member in [path / 'cgroup.procs', *path.rglob('*/cgroup.procs')]
                                 for p in member.read_text().split()}))
    except (OSError, KeyError, ValueError):
        return None


def proc_stats(pids):
    import psutil
    result = Counter()
    tcp_states = Counter()
    for pid in pids:
        try:
            process = psutil.Process(pid)
            with process.oneshot():
                result['rss_bytes'] += process.memory_info().rss
                result['threads'] += process.num_threads()
                result['fds'] += process.num_fds()
                io = process.io_counters()
                result['read_bytes'] += io.read_bytes
                result['write_bytes'] += io.write_bytes
            for connection in process.net_connections(kind='tcp'):
                tcp_states[connection.status] += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            result['unreadable_processes'] += 1
    return dict(result, tcp_states=dict(tcp_states))


def temporary_files(root):
    count = size = 0
    for directory in (root / 'reddit2telegram/tmp', Path('/tmp')):
        # Only inspect application-owned temporary directories in system /tmp.
        targets = directory.glob('r2t-*') if directory == Path('/tmp') else [directory]
        for target in targets:
            for path in target.rglob('*') if target.is_dir() else [target]:
                try:
                    if path.is_file() and not path.is_symlink():
                        size += path.stat().st_size
                        count += 1
                except OSError:
                    pass
    return dict(files=count, bytes=size)


def sample(manifest):
    result = dict(ts=time.time(), components={})
    for name, group in manifest['cgroups'].items():
        resource = cgroup_stats(Path(group))
        if resource is not None:
            resource.update(proc_stats(resource['pids']))
        result['components'][name] = resource
    application = [result['components'].get(name) for name in ('worker', 'scheduler')]
    application = [item for item in application if item is not None]
    result['application_memory_bytes'] = sum(item['memory_bytes'] for item in application)
    result['application_rss_bytes'] = sum(item.get('rss_bytes', 0) for item in application)
    result['application_cpu_usec'] = sum(item['cpu_usec'] for item in application)
    mongo = result['components'].get('mongodb')
    result['combined_memory_bytes'] = result['application_memory_bytes'] + (mongo['memory_bytes'] if mongo else 0)
    # Backend-independent indication of competing host activity.
    result['load_average'] = os.getloadavg()
    result['available_host_bytes'] = __import__('psutil').virtual_memory().available
    return result


def queue_observation(root):
    import pymongo
    import yaml
    config = yaml.safe_load((root / 'reddit2telegram/configs/prod.yml').read_text())
    client = pymongo.MongoClient(config['db']['host'], serverSelectionTimeoutMS=2000,
                                 connectTimeoutMS=2000, socketTimeoutMS=2000)
    try:
        tasks = client[config['db']['name']]['tasks']
        counts = {str(status): tasks.count_documents({'status': status}, maxTimeMS=2000)
                  for status in (1, 2, 4, 5)}
        oldest = tasks.find_one({'status': 1}, sort=[('created_at', 1)], projection={'created_at': 1})
        return dict(ts=time.time(), counts=counts,
                    oldest_wait_seconds=max(0, time.time() - oldest['created_at']) if oldest else 0)
    finally:
        client.close()


def distribution(values):
    values = sorted(v for v in values if v is not None and math.isfinite(v))
    if not values:
        return dict(count=0, average=None, median=None, p95=None, maximum=None)
    return dict(count=len(values), average=statistics.mean(values), median=statistics.median(values),
                p95=values[max(0, math.ceil(len(values) * .95) - 1)], maximum=values[-1], minimum=values[0])


def json_lines(path):
    if not path.exists():
        return []
    result = []
    for line in path.read_text().splitlines():
        try:
            result.append(json.loads(line))
        except ValueError:
            result.append(dict(event='malformed_record'))
    return result


def summarize(directory):
    manifest = read_json(directory / 'manifest.json')
    if not manifest:
        raise ValueError('Missing manifest')
    samples = [s for s in json_lines(directory / 'samples.jsonl') if 'components' in s]
    events = [e for e in json_lines(directory / 'events.jsonl')
              if manifest['started_at'] <= e.get('ts', -1) < manifest['deadline']]
    jobs = [e for e in events if e.get('event') == 'job_end']
    starts = [e for e in events if e.get('event') == 'job_start']
    cpu = []
    mongo_cpu = []
    cpu_seconds = 0
    discontinuities = 0
    for before, after in zip(samples, samples[1:]):
        dt = after['ts'] - before['ts']
        if dt <= 0:
            continue
        delta = after['application_cpu_usec'] - before['application_cpu_usec']
        if delta < 0:
            discontinuities += 1
        else:
            cpu_seconds += delta / 1e6
            cpu.append(delta / 1e6 / dt * 100)
        a = before['components'].get('mongodb')
        b = after['components'].get('mongodb')
        if a and b and b['cpu_usec'] >= a['cpu_usec']:
            mongo_cpu.append((b['cpu_usec'] - a['cpu_usec']) / 1e6 / dt * 100)
    counters = Counter()
    for job in jobs:
        counters.update(job.get('counters', {}))
    successes = sum(j.get('status') == 'success' for j in jobs)
    memory = [s['application_memory_bytes'] for s in samples]
    available_hours = (samples[-1]['ts'] - samples[0]['ts']) / 3600 if len(samples) >= 2 else 0
    trend = None
    if len(samples) >= 2:
        xs = [(s['ts'] - samples[0]['ts']) / 3600 for s in samples]
        xbar, ybar = statistics.mean(xs), statistics.mean(memory)
        divisor = sum((x - xbar) ** 2 for x in xs)
        trend = sum((x-xbar)*(y-ybar) for x,y in zip(xs,memory))/divisor if divisor else None
    gaps = [b['ts']-a['ts'] for a,b in zip(samples,samples[1:])]
    report = dict(schema=1, run_id=manifest['run_id'], label=manifest['label'],
                  started_at=manifest['started_at'], deadline=manifest['deadline'],
                  intended_seconds=DURATION, observed_hours=available_hours,
                  measurement_status=manifest.get('status'), source=manifest['source'],
                  runtime=manifest['runtime'], sample_count=len(samples),
                  expected_sample_count=DURATION//INTERVAL + 1,
                  sampling_gaps_seconds=distribution(gaps), cpu_counter_resets=discontinuities,
                  application_cpu_percent_one_core=distribution(cpu),
                  application_cpu_seconds=cpu_seconds,
                  cpu_seconds_per_successful_job=cpu_seconds/successes if successes else None,
                  application_memory_bytes=distribution(memory),
                  application_rss_bytes=distribution([s['application_rss_bytes'] for s in samples]),
                  combined_memory_bytes=distribution([s['combined_memory_bytes'] for s in samples]),
                  memory_linear_trend_bytes_per_hour=trend,
                  mongodb_cpu_percent_one_core=distribution(mongo_cpu),
                  mongodb_memory_bytes=distribution([s['components']['mongodb']['memory_bytes']
                                                     for s in samples if s['components'].get('mongodb')]),
                  job_processing_seconds=distribution([j.get('duration_seconds') for j in jobs]),
                  queue_wait_seconds=distribution([j.get('queue_wait_seconds') for j in jobs]),
                  jobs=dict(started=len(starts), completed=len(jobs), successful=successes,
                            failed=len(jobs)-successes,
                            starts_without_observed_end=len({j['task_id'] for j in starts} - {j['task_id'] for j in jobs})),
                  counters=dict(counters),
                  errors=dict(Counter(j['error_type'] for j in jobs if j.get('error_type'))),
                  caveats=['Sequential live workloads differ; no replay or historical baseline.',
                           'CPU is percent of one core; p95 uses nearest rank.',
                           'Job counters cover jobs completed within the window; boundary jobs are censored.',
                           'HTTP bytes are body bytes, not TLS traffic; Telegram fetches URL media remotely.',
                           'MongoDB is measured separately and may serve other workloads.',
                           'Kernel peaks are component lifetime peaks unless explicitly reset at start.'])
    report['component_kernel_peaks'] = {
        name: dict(bytes=max((s['components'][name]['kernel_peak_bytes'] for s in samples
                              if s['components'].get(name)), default=0),
                   scope='cgroup_lifetime', start_bytes=manifest['initial_components'].get(name, {}).get('kernel_peak_bytes'))
        for name in manifest['cgroups']}
    report['worker_fds'] = distribution([s['components']['worker'].get('fds')
                                       for s in samples if s['components'].get('worker')])
    report['worker_threads'] = distribution([s['components']['worker'].get('threads')
                                           for s in samples if s['components'].get('worker')])
    report['worker_unavailable_samples'] = sum(s['components'].get('worker') is None for s in samples)
    report['scheduler_runs'] = sum(e.get('event') == 'scheduler_end' for e in events)
    report['scheduler_submitted_jobs'] = sum(e.get('submitted_jobs', 0) for e in events
                                           if e.get('event') == 'scheduler_submitted')
    post_keys = [e['post_key'] for e in events if e.get('event') == 'post_record']
    report['observed_duplicate_post_records'] = len(post_keys)-len(set(post_keys))
    report['sampling_errors'] = json_lines(directory / 'sampling_errors.jsonl')
    report['source_changed'] = manifest.get('source_changed')
    report['worker_pid_sets_observed'] = sorted({tuple(s['components']['worker']['pids'])
                                               for s in samples if s['components'].get('worker')})
    for state in ('ESTABLISHED', 'CLOSE_WAIT'):
        report['worker_connections_' + state.lower()] = distribution([
            s['components']['worker'].get('tcp_states', {}).get(state, 0)
            for s in samples if s['components'].get('worker')])
    report['temporary_file_bytes'] = distribution([
        r['temporary_files']['bytes'] for r in json_lines(directory / 'queue.jsonl') if 'temporary_files' in r])
    report['queue_observations'] = json_lines(directory / 'queue.jsonl')
    atomic_json(directory / 'summary.json', report)
    return report


def install_scheduler_slice():
    path = Path.home() / '.config/systemd/user/r2tbench.slice'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('[Unit]\nDescription=r2t live benchmark scheduler accounting\nStopWhenUnneeded=no\n\n'
                    '[Slice]\nCPUAccounting=yes\nMemoryAccounting=yes\n')
    subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', '--user', 'start', 'r2tbench.slice'], check=True)
    group = command(['systemctl', '--user', 'show', 'r2tbench.slice', '-p', 'ControlGroup', '--value'])
    return '/sys/fs/cgroup' + group


def start(args):
    root = args.root.resolve()
    base = bench(root)
    state = base / 'state'
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (state / 'experiment.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        ledger = read_json(state / 'experiment.json', dict(runs={}))
        if args.label in ledger['runs']:
            raise ValueError('This configuration already has a run; repeating is prohibited')
        for item in ledger['runs'].values():
            if item['status'] == 'running':
                raise ValueError('A run is already active; reconcile it before starting another')
        # Verify required components before committing the one allowed run.
        worker_group = '/sys/fs/cgroup/system.slice/r2t_consumer_app.service'
        mongo_group = '/sys/fs/cgroup/system.slice/mongod.service'
        if not cgroup_stats(Path(worker_group)):
            raise ValueError('Production worker service is unavailable')
        selected = read_json(state / 'runtime.json', dict(label='python312'))
        if selected.get('label') != args.label:
            raise ValueError('Requested label does not match the selected production runtime')
        scheduler_group = install_scheduler_slice()
        run_id = args.label + '-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        directory = base / 'runs' / run_id
        directory.mkdir(parents=True, mode=0o700)
        started = time.time()
        manifest = dict(schema=1, run_id=run_id, label=args.label, status='running',
                        root=str(root), started_at=started, deadline=started+DURATION,
                        started_iso=stamp(), interval_seconds=INTERVAL,
                        events_path=str(directory / 'events.jsonl'),
                        source=fingerprint(root),
                        selected_runtime=selected,
                        runtime=dict(measurement_python=sys.version, measurement_executable=sys.executable,
                                     platform=platform.platform(), cpu_count=os.cpu_count(),
                                     dependencies={d.metadata['Name']: d.version for d in importlib.metadata.distributions()
                                                   if d.metadata['Name']}),
                        cgroups=dict(worker=worker_group, scheduler=scheduler_group, mongodb=mongo_group))
        worker_pid = int(command(['systemctl', 'show', 'r2t_consumer_app.service', '-p', 'MainPID', '--value']))
        worker_executable = str((Path('/proc') / str(worker_pid) / 'exe').resolve())
        expected = Path(selected.get('consumer', [sys.executable])[0]).resolve()
        if worker_executable != str(expected):
            raise ValueError('Production executable does not match the selected implementation')
        manifest['runtime']['worker_executable'] = worker_executable
        manifest['runtime']['worker_pid'] = worker_pid
        manifest['initial_components'] = {name: cgroup_stats(Path(path)) or {}
                                          for name,path in manifest['cgroups'].items()}
        atomic_json(directory / 'manifest.json', manifest)
        ledger['runs'][args.label] = dict(run_id=run_id, directory=str(directory),
                                        started_at=started, deadline=manifest['deadline'], status='running')
        atomic_json(state / 'experiment.json', ledger)
        atomic_json(state / 'active.json', manifest)
        script = Path(__file__).resolve()
        try:
            subprocess.run(['systemd-run', '--user', '--unit=r2tbench-' + args.label,
                            '--property=Restart=on-failure', '--property=RestartSec=5',
                            '--property=RuntimeMaxSec=86520', '--property=UMask=0077',
                            sys.executable, str(script), 'collect', '--directory', str(directory)], check=True)
        except BaseException:
            manifest['status'] = 'launch_failed'
            atomic_json(directory / 'manifest.json', manifest)
            ledger['runs'][args.label]['status'] = 'launch_failed'
            atomic_json(state / 'experiment.json', ledger)
            (state / 'active.json').unlink(missing_ok=True)
            raise
        print(json.dumps(dict(run_id=run_id, started=manifest['started_iso'],
                              deadline=datetime.fromtimestamp(manifest['deadline'],timezone.utc).isoformat(),
                              directory=str(directory)), indent=2))


def collect(directory):
    manifest = read_json(directory / 'manifest.json')
    if not manifest or manifest['status'] != 'running':
        raise ValueError('Run is not active')
    root = Path(manifest['root'])
    terminated = []
    def stop(signum, frame):
        terminated.append(signum)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    last_queue = 0
    next_tick = time.time()
    while not terminated:
        now = time.time()
        if now > manifest['deadline']:
            break
        try:
            record = sample(manifest)
            if record['ts'] <= manifest['deadline']:
                append(directory / 'samples.jsonl', record)
        except Exception as exc:
            append(directory / 'sampling_errors.jsonl', dict(ts=time.time(), error_type=type(exc).__name__))
        if now - last_queue >= 30 and manifest['deadline'] - time.time() > 5:
            last_queue = now
            try:
                observation = queue_observation(root)
                observation['temporary_files'] = temporary_files(root)
                append(directory / 'queue.jsonl', observation)
            except Exception as exc:
                append(directory / 'sampling_errors.jsonl', dict(ts=time.time(), component='queue', error_type=type(exc).__name__))
        remaining = manifest['deadline'] - time.time()
        if remaining <= 0:
            break
        next_tick += INTERVAL
        if next_tick < time.time():
            next_tick = time.time() + INTERVAL
        time.sleep(max(0, min(next_tick-time.time(), remaining)))
    # A delayed restart must never attribute post-deadline work to the window.
    # Allow only the immediate boundary counter read, with explicit lateness.
    boundary_lateness = max(0, time.time()-manifest['deadline'])
    if boundary_lateness <= 1:
        try:
            final = sample(manifest)
            final['boundary_read_lateness_seconds'] = max(0, final['ts']-manifest['deadline'])
            append(directory / 'samples.jsonl', final)
        except Exception as exc:
            append(directory / 'sampling_errors.jsonl', dict(ts=time.time(), error_type=type(exc).__name__))
    else:
        append(directory / 'sampling_errors.jsonl', dict(ts=time.time(), error_type='missed_deadline_boundary',
                                                         lateness_seconds=boundary_lateness))
    manifest['finished_iso'] = stamp()
    manifest['status'] = 'interrupted' if terminated else 'finished'
    manifest['source_at_end'] = fingerprint(root)
    manifest['source_changed'] = manifest['source_at_end'] != manifest['source']
    atomic_json(directory / 'manifest.json', manifest)
    summary = summarize(directory)
    state = bench(root) / 'state'
    ledger = read_json(state / 'experiment.json')
    ledger['runs'][manifest['label']]['status'] = manifest['status']
    atomic_json(state / 'experiment.json', ledger)
    active = read_json(state / 'active.json')
    if active and active['run_id'] == manifest['run_id']:
        (state / 'active.json').unlink(missing_ok=True)
    print(json.dumps(dict(run_id=manifest['run_id'], status=manifest['status'],
                          sample_count=summary['sample_count'], summary=str(directory/'summary.json'))), flush=True)


def schedule(root):
    root = root.resolve()
    manifest = read_json(bench(root) / 'state/active.json')
    app = root / 'reddit2telegram'
    invocation = [sys.executable, str(app / 'task_queue_cron_app.py')]
    if not manifest or not manifest['started_at'] <= time.time() < manifest['deadline']:
        os.chdir(app)
        os.execv(sys.executable, invocation)
    # Actual scheduler, in its own accounting group; no second scheduler is run.
    started = time.monotonic()
    status = subprocess.run(['systemd-run', '--user', '--quiet', '--wait', '--pipe', '--collect',
                             '--unit=r2tbench-scheduler-' + uuid.uuid4().hex[:8],
                             '--slice=r2tbench.slice', '--property=WorkingDirectory=' + str(app),
                             *invocation], cwd=app).returncode
    now = time.time()
    if now < manifest['deadline']:
        append(Path(manifest['events_path']), dict(schema=1, run_id=manifest['run_id'],
               event='scheduler_end', ts=now, status=status, wall_seconds=time.monotonic()-started))
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    launch = sub.add_parser('start')
    launch.add_argument('--root', type=Path, required=True)
    launch.add_argument('--label', choices=LABELS, required=True)
    observation = sub.add_parser('collect')
    observation.add_argument('--directory', type=Path, required=True)
    scheduler = sub.add_parser('schedule')
    scheduler.add_argument('--root', type=Path, required=True)
    summary = sub.add_parser('summarize')
    summary.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    if args.action == 'start':
        start(args)
    elif args.action == 'collect':
        collect(args.directory)
    elif args.action == 'schedule':
        sys.exit(schedule(args.root))
    else:
        print(json.dumps(summarize(args.directory), indent=2))


if __name__ == '__main__':
    main()
