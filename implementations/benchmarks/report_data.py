"""Read-only analysis of the seven fresh live windows; no application requests.

Exports use aggregate measurements and allowlisted build/source metadata.
Raw PIDs, job IDs, process arguments, URLs, payloads and configuration values
are never part of the portable report bundle.
"""

from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import statistics

LABELS = ('python312', 'python315', 'rust', 'swift', 'cpp', 'c', 'go')
NAMES = dict(zip(LABELS, ('Python 3.12', 'Python 3.15', 'Rust', 'Swift', 'C++', 'C', 'Go')))
FINAL_STATUSES = {'finished', 'interrupted', 'launch_failed'}
PERIOD = 5
MAX_INTERVAL = PERIOD * 2
SAFE_KEY = re.compile(r'^[A-Za-z][A-Za-z0-9_.-]{0,79}$')


class EvidenceError(ValueError):
    pass


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def distribution(values, weights=None):
    pairs = [(v, 1 if weights is None else w) for v, w in
             zip(values, [1] * len(values) if weights is None else weights)
             if finite(v) and finite(w) and w > 0]
    if not pairs:
        return dict(count=0, average=None, median=None, p95=None, maximum=None, minimum=None)
    ordered = sorted(v for v, _ in pairs)
    return dict(count=len(ordered),
        average=sum(v*w for v, w in pairs)/sum(w for _, w in pairs),
        median=statistics.median(ordered),
        p95=ordered[math.ceil(len(ordered)*.95)-1], maximum=ordered[-1], minimum=ordered[0])


def read_records(path, receipts):
    if not path.exists():
        receipts[path.name] = dict(present=False)
        return []
    raw = path.read_bytes()
    rows, malformed, incomplete_tail = [], 0, 0
    lines = raw.splitlines(keepends=True)
    for index, line in enumerate(lines):
        try:
            value = json.loads(line)
            if isinstance(value, dict):
                rows.append(value)
            else:
                malformed += 1
        except (ValueError, UnicodeError):
            if index == len(lines)-1 and not line.endswith(b'\n'):
                incomplete_tail += 1
            else:
                malformed += 1
    receipts[path.name] = dict(present=True, sha256=hashlib.sha256(raw).hexdigest(),
        bytes=len(raw), records=len(rows), malformed_records=malformed,
        incomplete_tail_records=incomplete_tail)
    return rows


def read_manifest(path, receipts):
    raw = path.read_bytes()
    receipts[path.name] = dict(present=True, sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
    return json.loads(raw)


def iso(stamp):
    return datetime.fromtimestamp(stamp, timezone.utc).isoformat()


def parse_iso(value):
    try:
        return datetime.fromisoformat(value).timestamp()
    except (ValueError, TypeError):
        return None


def coverage(intervals):
    merged = []
    for begin, end in sorted(intervals):
        if not merged or begin > merged[-1][1]:
            merged.append([begin, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return sum(end-begin for begin, end in merged)


def counter_series(samples, names):
    seconds, intervals, all_intervals, rates, weights = 0.0, [], [], [], []
    resets = missing = long_gaps = nonpositive = 0
    for before, after in zip(samples, samples[1:]):
        dt = after['ts']-before['ts']
        if dt <= 0:
            nonpositive += 1
            continue
        old = [before['components'].get(name) for name in names]
        new = [after['components'].get(name) for name in names]
        if not all(item and finite(item.get('cpu_usec')) for item in [*old, *new]):
            missing += 1
            continue
        deltas = [b['cpu_usec']-a['cpu_usec'] for a, b in zip(old, new)]
        if any(delta < 0 for delta in deltas):
            resets += 1
            continue
        amount = sum(deltas)/1e6
        seconds += amount
        all_intervals.append((before['ts'], after['ts']))
        if dt <= MAX_INTERVAL:
            intervals.append((before['ts'], after['ts']))
            rates.append(amount/dt*100)
            weights.append(dt)
        else:
            long_gaps += 1
    return dict(seconds=seconds if all_intervals else None, sampled_percent_one_core=distribution(rates, weights),
        valid_counter_intervals=len(all_intervals), total_counter_coverage_seconds=coverage(all_intervals),
        short_interval_coverage_seconds=coverage(intervals),
        short_interval_seconds=sum(weights), counter_reset_intervals=resets,
        missing_component_intervals=missing, long_gap_intervals=long_gaps,
        nonpositive_intervals=nonpositive)


def component_values(samples, names, key):
    values = []
    for sample in samples:
        items = [sample['components'].get(name) for name in names]
        if all(item is not None and finite(item.get(key)) for item in items):
            values.append(sum(item[key] for item in items))
    return values


def slope(samples):
    pairs = []
    for sample in samples:
        values = component_values([sample], ('worker', 'scheduler'), 'memory_bytes')
        if values:
            pairs.append((sample['ts']/3600, values[0]))
    if len(pairs) < 2:
        return None
    xmean, ymean = statistics.mean(x for x, _ in pairs), statistics.mean(y for _, y in pairs)
    divisor = sum((x-xmean)**2 for x, _ in pairs)
    return sum((x-xmean)*(y-ymean) for x, y in pairs)/divisor if divisor else None


def build_receipt(manifest):
    selected = manifest.get('selected_runtime', {})
    detail = selected.get('describe', selected.get('native_metadata', selected))
    safe = {}
    for key in ('version', 'compiler', 'profile', 'standard', 'language_mode', 'optimization',
                'architecture', 'allocator', 'mongodb_client', 'http_client'):
        value = detail.get(key, selected.get(key))
        if isinstance(value, str) and len(value) <= 1500 and '://' not in value and '@' not in value:
            safe[key] = value
    for key in ('gil_enabled', 'jit_enabled'):
        if isinstance(selected.get(key), bool):
            safe[key] = selected[key]
    for key in ('artifact_sha256', 'source_commit'):
        value = selected.get(key, detail.get(key))
        if isinstance(value, str) and re.fullmatch(r'[a-f0-9]{40}|[a-f0-9]{64}', value):
            safe[key] = value
    dependencies = detail.get('dependencies', selected.get('dependencies'))
    if isinstance(dependencies, dict):
        safe['application_dependencies'] = {k: v for k, v in dependencies.items()
            if isinstance(k, str) and re.fullmatch(r'[-A-Za-z0-9._/]+', k)
            and isinstance(v, str) and re.fullmatch(r'[-A-Za-z0-9._+]+', v)}
    elif isinstance(dependencies, list):
        safe['application_dependencies'] = [
            dict(module=item['module'], version=item['version'], **(
                {'sum': item['sum']} if isinstance(item.get('sum'), str)
                and re.fullmatch(r'h1:[A-Za-z0-9+/=]+', item['sum']) else {}))
            for item in dependencies if isinstance(item, dict)
            and isinstance(item.get('module'), str)
            and re.fullmatch(r'[-A-Za-z0-9._/]+', item['module'])
            and isinstance(item.get('version'), str)
            and re.fullmatch(r'[-A-Za-z0-9._+]+', item['version'])]
    runtime = manifest.get('runtime', {})
    safe['observer_python'] = runtime.get('measurement_python', '').splitlines()[0]
    safe['host_logical_cpus'] = runtime.get('cpu_count')
    source = manifest.get('source', {})
    safe['source'] = {key: source[key] for key in ('commit', 'tracked_source_sha256', 'dirty_diff_sha256')
                      if isinstance(source.get(key), str) and re.fullmatch(r'[a-f0-9]{40}|[a-f0-9]{64}', source[key])}
    safe['configuration_sha256'] = {Path(key).name: value
        for key, value in source.get('configuration_sha256', {}).items()
        if Path(key).name in ('prod.yml', 'own.cron')
        and isinstance(value, str) and re.fullmatch(r'[a-f0-9]{64}', value)}
    return safe


NOTE_DESCRIPTIONS = {
    'deployment_environment_correction': 'The first cron scheduler invocation failed because its user-systemd bus environment was absent. '
                                         'Cron bus variables were corrected; the window was not restarted or extended.',
    'development_isolation': 'Implementation preparation was isolated from the measured production checkout and environment.',
    'process_sampler_started': 'Supplementary process-role observations began after the original window start.',
    'process_sampler_finished': 'Supplementary process observations stopped; the original deadline was retained.',
    'process_sampler_source': 'Supplementary sampler source identity was recorded.',
}


def note_receipts(notes):
    result = []
    for row in notes:
        event = row.get('event', row.get('kind', 'operator_note'))
        if not isinstance(event, str) or not SAFE_KEY.fullmatch(event):
            event = 'operator_note'
        item = dict(event=event)
        if finite(row.get('ts')):
            item['ts'] = row['ts']
        for key in ('delay_from_window_start_seconds', 'samples', 'sampling_errors', 'original_deadline'):
            if finite(row.get(key)):
                item[key] = row[key]
        item['description'] = NOTE_DESCRIPTIONS.get(event, 'An operator incident or change was recorded; review the private source note.')
        result.append(item)
    return result


def process_summary(rows, start, end):
    rows = [r for r in rows if finite(r.get('ts')) and start <= r['ts'] <= end]
    if not rows:
        return dict(available=False, samples=0, coverage_seconds=0, coverage_fraction=0,
                    ffmpeg_cpu_scope='unavailable')
    good = [r for r in rows if r.get('worker_identities') and r.get('unreadable_processes', 0) == 0]
    intervals, rates, weights = [], defaultdict(list), []
    totals = dict(worker=0.0, helpers=0.0)
    resets = helper_snapshot_decreases = valid_counter_intervals = 0
    helper_high = None
    previous = None
    ffmpeg_cpu_lower_bound = 0.0
    seen_ffmpeg = {}
    for row in rows:
        for process in row.get('processes', []):
            if process.get('role') != 'ffmpeg' or not finite(process.get('cpu_seconds')):
                continue
            key = (process.get('pid'), process.get('created_at'))
            old = seen_ffmpeg.get(key)
            if old is not None:
                ffmpeg_cpu_lower_bound += max(0, process['cpu_seconds']-old)
            elif finite(process.get('created_at')) and process['created_at'] >= rows[0]['ts']:
                ffmpeg_cpu_lower_bound += process['cpu_seconds']
            seen_ffmpeg[key] = process['cpu_seconds']
    for row in good:
        if previous is None or previous['worker_identities'] != row['worker_identities']:
            if previous is not None:
                resets += 1
            previous, helper_high = row, row['helpers_cpu_seconds']
            continue
        dt = row['ts']-previous['ts']
        worker_delta = row['worker_cpu_seconds']-previous['worker_cpu_seconds']
        if row['helpers_cpu_seconds'] < helper_high:
            helper_snapshot_decreases += 1
        helper_delta = max(0, row['helpers_cpu_seconds']-helper_high)
        helper_high = max(helper_high, row['helpers_cpu_seconds'])
        if dt > 0 and worker_delta >= 0:
            valid_counter_intervals += 1
            totals['worker'] += worker_delta
            totals['helpers'] += helper_delta
            if dt <= MAX_INTERVAL:
                intervals.append((previous['ts'], row['ts']))
                weights.append(dt)
                rates['worker'].append(worker_delta/dt*100)
                rates['helpers'].append(helper_delta/dt*100)
        elif worker_delta < 0:
            resets += 1
        previous = row
    roles = {}
    for name in ('worker', 'ffmpeg', 'other_helper'):
        values = [r.get('roles', {}).get(name) for r in good]
        roles[name] = {key: distribution([v.get(key) for v in values if isinstance(v, dict)])
                       for key in ('rss_bytes', 'fds', 'threads', 'processes')}
        roles[name]['samples_with_live_process'] = sum(v.get('processes', 0) > 0 for v in values if v)
    exposure = max(0, end-start)
    return dict(available=True, samples=len(rows), valid_samples=len(good),
        first_sample=rows[0]['ts'], last_sample=rows[-1]['ts'],
        first_sample_delay_seconds=max(0, rows[0]['ts']-start),
        coverage_seconds=coverage(intervals), coverage_fraction=coverage(intervals)/exposure if exposure else None,
        roles=roles, worker_cpu_seconds=totals['worker'] if valid_counter_intervals else None,
        helpers_cpu_seconds=totals['helpers'] if valid_counter_intervals else None,
        worker_cpu_percent_one_core=distribution(rates['worker'], weights),
        helpers_cpu_percent_one_core=distribution(rates['helpers'], weights),
        ffmpeg_observed_cpu_seconds_lower_bound=ffmpeg_cpu_lower_bound,
        ffmpeg_cpu_scope='Lower bound from observed PIDs; unobserved child lifetimes and tails are missing. '
                         'Helpers CPU includes ffmpeg plus maintenance helpers, including reaped work.',
        root_identity_changes=resets, helper_snapshot_decreases=helper_snapshot_decreases)


def event_summary(events):
    starts = defaultdict(list)
    ends, matched, completed_ids = [], [], Counter()
    counters, errors, modules = Counter(), Counter(), defaultdict(Counter)
    orphan_ends = 0
    for row in sorted(events, key=lambda r: r['ts']):
        kind, task = row.get('event'), row.get('task_id')
        if kind == 'job_start':
            starts[task].append(row)
        elif kind == 'job_end':
            ends.append(row)
            completed_ids[task] += 1
            candidates = starts.get(task, [])
            if candidates:
                duration = row.get('duration_seconds', 0)
                duration = duration if finite(duration) else 0
                index = min(range(len(candidates)),
                            key=lambda i: abs(row['ts']-candidates[i]['ts']-duration))
                begin = candidates.pop(index)
                if begin.get('module') == row.get('module'):
                    matched.append(row)
                else:
                    orphan_ends += 1
                    candidates.insert(index, begin)
            else:
                orphan_ends += 1
            values = {key: value for key, value in row.get('counters', {}).items()
                      if isinstance(key, str) and re.fullmatch(r'[a-z][a-z0-9_]{0,79}', key)
                      and finite(value) and value >= 0}
            counters.update(values)
            error = row.get('error_type')
            if isinstance(error, str) and SAFE_KEY.fullmatch(error):
                errors[error] += 1
            module = row.get('module')
            if isinstance(module, str) and re.fullmatch(r'[a-zA-Z0-9_]{1,80}', module):
                modules[module]['completed'] += 1
                modules[module]['successful'] += row.get('status') == 'success'
                modules[module]['telegram_messages'] += values.get('telegram_messages', 0)
    successes = sum(row.get('status') == 'success' for row in ends)
    scheduler = [r for r in events if r.get('event') == 'scheduler_end']
    posts = [r.get('post_key') for r in events if r.get('event') == 'post_record' and isinstance(r.get('post_key'), str)]
    return dict(started=sum(r.get('event') == 'job_start' for r in events),
        completed=len(ends), successful=successes, failed=len(ends)-successes,
        success_fraction=successes/len(ends) if ends else None,
        paired_executions=len(matched), orphan_end_records=orphan_ends,
        starts_without_observed_end=sum(len(v) for v in starts.values()),
        task_ids_with_multiple_completions=sum(v > 1 for v in completed_ids.values()),
        processing_seconds=distribution([r.get('duration_seconds') for r in matched]),
        queue_wait_seconds=distribution([r.get('queue_wait_seconds') for r in matched]),
        counters=dict(counters), errors=dict(errors), modules={key: dict(v) for key, v in modules.items()},
        scheduler_runs=len(scheduler), scheduler_failures=sum(r.get('status') != 0 for r in scheduler),
        scheduler_wall_seconds=distribution([r.get('wall_seconds') for r in scheduler]),
        submitted_jobs=sum(r.get('submitted_jobs', 0) for r in events if r.get('event') == 'scheduler_submitted'),
        post_records=len(posts), repeated_source_channel_records=len(posts)-len(set(posts)))


def analyze_run(directory):
    receipts = {}
    manifest = read_manifest(directory / 'manifest.json', receipts)
    label, start, deadline = manifest.get('label'), manifest.get('started_at'), manifest.get('deadline')
    if label not in LABELS or not finite(start) or not finite(deadline) or abs(deadline-start-86400) > .001:
        raise EvidenceError('Run identity or original 24-hour bounds are invalid')
    if manifest.get('selected_runtime', {}).get('label') != label:
        raise EvidenceError('The selected runtime label does not match the run')
    status = manifest.get('status')
    finished = parse_iso(manifest.get('finished_iso'))
    end = min(deadline, finished) if status == 'interrupted' and finished is not None else deadline
    raw_samples = read_records(directory / 'samples.jsonl', receipts)
    samples = [s for s in raw_samples if isinstance(s.get('components'), dict)
               and finite(s.get('ts')) and start <= s['ts'] <= end]
    all_events = read_records(directory / 'events.jsonl', receipts)
    events = [e for e in all_events if finite(e.get('ts')) and start <= e['ts'] < end
              and e.get('run_id') == manifest.get('run_id')]
    queues = [q for q in read_records(directory / 'queue.jsonl', receipts)
              if finite(q.get('ts')) and start <= q['ts'] <= end]
    notes = read_records(directory / 'notes.jsonl', receipts)
    process = read_records(directory / 'processes.jsonl', receipts)
    sampling_errors = read_records(directory / 'sampling_errors.jsonl', receipts)
    process_errors = read_records(directory / 'process_sampling_errors.jsonl', receipts)
    components = {}
    for name, group in (('application', ('worker', 'scheduler')), ('worker_cgroup', ('worker',)),
                        ('scheduler', ('scheduler',)), ('mongodb', ('mongodb',)),
                        ('combined', ('worker', 'scheduler', 'mongodb'))):
        components[name] = dict(cpu=counter_series(samples, group),
            memory_bytes=distribution(component_values(samples, group, 'memory_bytes')),
            rss_bytes=distribution(component_values(samples, group, 'rss_bytes')),
            file_cache_bytes=distribution(component_values(samples, group, 'file_cache_bytes')))
    jobs = event_summary(events)
    cpu_seconds = components['application']['cpu']['seconds']
    bins = defaultdict(list)
    for sample in samples:
        values = component_values([sample], ('worker', 'scheduler'), 'memory_bytes')
        if values:
            bins[min(23, int((sample['ts']-start)//3600))].append(values[0])
    worker = [s['components'].get('worker') for s in samples if s['components'].get('worker') is not None]
    peaks = {name: dict(scope='cgroup_lifetime', bytes=max(
            (s['components'][name]['kernel_peak_bytes'] for s in samples if s['components'].get(name)
             and finite(s['components'][name].get('kernel_peak_bytes'))), default=None))
             for name in ('worker', 'scheduler', 'mongodb')}
    exposure = max(0, end-start)
    result = dict(label=label, name=NAMES[label], run_id=manifest.get('run_id'), status=status,
        started_at=start, deadline=deadline, effective_end=end, started_iso=iso(start), ended_iso=iso(end),
        exposure_seconds=exposure, scheduled_seconds=86400, sample_count=len(samples),
        sampling_coverage_fraction=components['application']['cpu']['short_interval_coverage_seconds']/exposure if exposure else None,
        excluded_after_window_samples=sum(finite(s.get('ts')) and s['ts'] > end for s in raw_samples),
        sampling_gaps_seconds=distribution([b['ts']-a['ts'] for a, b in zip(samples, samples[1:]) if b['ts'] > a['ts']]),
        sampling_errors=len(sampling_errors), process_sampling_errors=len(process_errors),
        source_changed=manifest.get('source_changed'), build=build_receipt(manifest),
        components=components, jobs=jobs,
        cpu_seconds_per_completed_job=cpu_seconds/jobs['completed'] if finite(cpu_seconds) and jobs['completed'] else None,
        cpu_seconds_per_successful_job=cpu_seconds/jobs['successful'] if finite(cpu_seconds) and jobs['successful'] else None,
        memory_linear_trend_bytes_per_hour=slope(samples),
        hourly_application_memory_bytes=[statistics.mean(bins[h]) if bins[h] else None for h in range(24)],
        worker_fds=distribution([s.get('fds') for s in worker]),
        worker_threads=distribution([s.get('threads') for s in worker]),
        worker_unavailable_samples=sum(s['components'].get('worker') is None for s in samples),
        initial_worker_pid_absent_samples=sum(
            manifest.get('runtime', {}).get('worker_pid') not in s.get('pids', []) for s in worker),
        worker_established_connections=distribution([s.get('tcp_states', {}).get('ESTABLISHED', 0)
            for s in worker if s.get('unreadable_processes', 0) == 0]),
        temporary_file_bytes=distribution([q.get('temporary_files', {}).get('bytes') for q in queues]),
        temporary_file_count=distribution([q.get('temporary_files', {}).get('files') for q in queues]),
        queued_backlog=distribution([q['counts'].get('1', 0)+q['counts'].get('5', 0)
            for q in queues if isinstance(q.get('counts'), dict) and '1' in q['counts'] and '5' in q['counts']]),
        oldest_queued_seconds=distribution([q.get('oldest_wait_seconds') for q in queues]),
        queue_observation_count=len(queues), kernel_peaks=peaks,
        processes=process_summary(process, start, end), notes=note_receipts(notes),
        source_receipts=receipts)
    return result


METHODS = dict(cpu='Percent of one logical core. Means weight short-interval CPU readings by interval seconds. '
                  'Medians/P95 use the short-interval readings; intervals over 10 seconds are excluded from distributions. '
                  'Cumulative CPU totals retain valid monotonic deltas across longer gaps.',
    memory='Sampled cgroup memory includes file cache and ffmpeg/helper children. '
           'RSS is process resident memory. Sample maxima are window observations; kernel peaks are cgroup lifetime values.',
    percentiles='Nearest-rank P95. Memory/timing means and medians describe eligible observations, not confidence intervals.',
    timing='Processing/queue distributions use matched start/end executions inside the window. '
           'Unfinished boundary jobs are censored. Counters summarize observed job-end records.',
    cpu_per_job='Application CPU includes worker/helpers/scheduler work, including censored jobs; '
                'the denominator is observed completed or successful jobs as labeled.',
    coverage='Fraction of the exposure spanned by consecutive complete-component samples at most 10 seconds apart. '
             'Post-deadline boundary reads are excluded; no post-deadline work is interpolated into results.',
    processes='Supplementary process snapshots separate observed RSS. FFmpeg-specific CPU is an observed lower bound; '
              'short lifetimes can be missed. Helpers CPU includes ffmpeg and other maintenance subprocesses.',
    http='Consumed decoded HTTP body bytes from completed jobs; excludes TLS/framing and Telegram remote URL downloads.',
    reliability='Job success is the application task outcome, not proof of a delivered post. '
                'Repeated source/channel records are observed records, not a direct audit of Telegram duplicates.',
    comparison='One fresh sequential live window per configuration; no replay, historical baseline or repeats. '
               'Workloads, upstream latency, media and libraries differ. This is not a causal language-speed experiment.')


def analyze_experiment(runs_directory):
    ledger_path = runs_directory.parent / 'state' / 'experiment.json'
    if not ledger_path.exists():
        raise EvidenceError('The original experiment ledger is required')
    ledger_raw = ledger_path.read_bytes()
    ledger = json.loads(ledger_raw)
    directories = [path.parent for path in runs_directory.glob('*/manifest.json')]
    by_label = {}
    for directory in directories:
        result = analyze_run(directory)
        entry = ledger.get('runs', {}).get(result['label'])
        if not entry or entry.get('run_id') != result['run_id'] or entry.get('started_at') != result['started_at'] or entry.get('deadline') != result['deadline']:
            raise EvidenceError('A run does not match the original experiment ledger')
        if entry.get('status') != result['status']:
            raise EvidenceError('Manifest/ledger finalization is in transition; read again after it completes')
        if result['label'] in by_label:
            raise EvidenceError('Multiple runs for a configuration; repetitions cannot be silently selected')
        by_label[result['label']] = result
    ordered = [by_label[label] for label in LABELS if label in by_label]
    missing = [label for label in LABELS if label not in by_label]
    active = [r['label'] for r in ordered if r['status'] not in FINAL_STATUSES]
    overlaps = []
    chronological = sorted(ordered, key=lambda r: r['started_at'])
    for before, after in zip(chronological, chronological[1:]):
        if after['started_at'] < before['effective_end']:
            overlaps.append([before['label'], after['label']])
    return dict(schema=1, expected_labels=list(LABELS), runs=ordered, missing_labels=missing,
        unfinished_labels=active, overlapping_windows=overlaps,
        final_ready=not missing and not active and not overlaps,
        methods=METHODS, ledger_sha256=hashlib.sha256(ledger_raw).hexdigest(), evidence_cutoff=max((r['effective_end'] for r in ordered
            if r['status'] in FINAL_STATUSES), default=None))


def require_final(bundle):
    if not bundle['final_ready']:
        raise EvidenceError('Final image requires seven finalized, non-overlapping fresh windows; '
            f"missing={','.join(bundle['missing_labels'])}; unfinished={','.join(bundle['unfinished_labels'])}")
