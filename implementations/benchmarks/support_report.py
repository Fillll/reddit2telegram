"""Separate fixed-48h Go support report; never changes the 24h comparison."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import time

from report_data import (EvidenceError, METHODS, build_receipt, component_values,
                         counter_series, distribution, event_summary, finite,
                         iso, parse_iso, process_summary, read_manifest, read_records)


SUPPORT_MODULES = ('tech_anniversary', 'tech_store_stat', 'tech_weekly_radar',
                   'tech_receiver', 'tech_cleaner')
CASE_NAMES = ('receiver_index_conflict', 'anniversary_delivery_and_yearly_dedup',
              'anniversary_uncertainty_hold', 'milestone_crossing_delivery_and_resume',
              'weekly_report_delivery', 'receiver_channel_intake_delivery',
              'cleaner_isolated_files_and_tasks', 'milestone_live_reddit_candidate')


def load(path):
    return json.loads(path.read_text())


def source_receipt(path):
    raw = path.read_bytes()
    return dict(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))


def mongo_utc(value):
    """PyMongo's default naive datetimes are UTC, regardless of render host TZ."""
    try:
        stamp = datetime.fromisoformat(value)
        return stamp.replace(tzinfo=timezone.utc).timestamp() if stamp.tzinfo is None else stamp.timestamp()
    except (TypeError, ValueError):
        return None


def holds(before, after):
    """Compare inherited parts by private identity; export aggregate counts only."""
    current = {e['event_id_sha256']: e for e in after['anniversary_events']}
    result = Counter()
    for event in before['anniversary_events']:
        row = current.get(event['event_identity_sha256'])
        parts = {p['index']: p for p in row['parts']} if row else {}
        for old in event['parts']:
            if old['state'] not in ('sent', 'uncertain', 'sending'):
                continue
            result['inherited_'+old['state']] += 1
            new = parts.get(old['index'])
            same = new is not None and all(new.get(k) == old.get(k)
                for k in ('state', 'attempts', 'message_id_count', 'message_ids_sha256'))
            result[('unchanged_' if same else 'changed_or_absent_')+old['state']] += 1
    return dict(result)


def analyze(directory, before_path, after_path, cases_path, review_path, final=True):
    receipts = {}
    manifest = read_manifest(directory/'manifest.json', receipts)
    start, deadline = manifest['started_at'], manifest['deadline']
    if (manifest.get('label') != 'go' or manifest.get('duration_seconds') != 172800
            or not finite(start) or not finite(deadline) or deadline-start != 172800
            or manifest.get('run_id') != directory.name
            or manifest.get('selected_runtime', {}).get('label') != 'go'
            or manifest.get('campaign') != 'go-support-48h'):
        raise EvidenceError('Expected the separately authorized fixed 48-hour Go campaign')
    ledger_path = directory.parent.parent/'state/experiment.json'
    ledger = load(ledger_path)
    entry = ledger['runs']['go']
    if entry['run_id'] != manifest['run_id'] or entry['deadline'] != deadline:
        raise EvidenceError('Campaign ledger and manifest differ')
    if final and (time.time() < deadline or manifest.get('status') != 'finished'
            or entry.get('status') != 'finished'
            or (parse_iso(manifest.get('finished_iso')) or 0) < deadline
            or manifest.get('source_changed') is not False
            or manifest.get('source_at_end') != manifest.get('source')):
        raise EvidenceError('Full fixed window, final ledger and unchanged source are required')
    end = deadline if final else min(time.time(), deadline)
    samples_raw = read_records(directory/'samples.jsonl', receipts)
    samples = [r for r in samples_raw if isinstance(r.get('components'), dict)
               and finite(r.get('ts')) and start <= r['ts'] <= end]
    events_raw = read_records(directory/'events.jsonl', receipts)
    foreign = sum(r.get('run_id') != manifest['run_id'] for r in events_raw)
    events = [r for r in events_raw if r.get('run_id') == manifest['run_id']
              and finite(r.get('ts')) and start <= r['ts'] < end]
    queue = [r for r in read_records(directory/'queue.jsonl', receipts)
             if finite(r.get('ts')) and start <= r['ts'] <= end]
    processes = read_records(directory/'processes.jsonl', receipts)
    read_records(directory/'notes.jsonl', receipts)
    sampling_errors = read_records(directory/'sampling_errors.jsonl', receipts)
    process_errors = read_records(directory/'process_sampling_errors.jsonl', receipts)
    if final and (foreign or any(r.get('malformed_records', 0)
            or r.get('incomplete_tail_records', 0) for r in receipts.values())):
        raise EvidenceError('Foreign, malformed or unfinished evidence requires review')
    components = {}
    for name, group in (('application', ('worker', 'scheduler')),
                        ('worker', ('worker',)), ('scheduler', ('scheduler',)),
                        ('mongodb', ('mongodb',)), ('combined', ('worker', 'scheduler', 'mongodb'))):
        components[name] = dict(cpu=counter_series(samples, group),
            memory_bytes=distribution(component_values(samples, group, 'memory_bytes')),
            rss_bytes=distribution(component_values(samples, group, 'rss_bytes')),
            file_cache_bytes=distribution(component_values(samples, group, 'file_cache_bytes')))
    jobs = event_summary(events, receipts['events.jsonl']['present'])
    hourly = []
    for hour in range(48):
        a, b = start+3600*hour, start+3600*(hour+1)
        rows = [r for r in samples if a <= r['ts'] < b]
        # Reuse interval logic with one previous observation so no whole interval
        # is lost at an hourly display boundary. Global statistics use all rows.
        previous = next((r for r in reversed(samples) if r['ts'] < a), None)
        cpu_rows = ([previous] if previous else [])+rows
        cpu = counter_series(cpu_rows, ('worker', 'scheduler'))
        mem = distribution(component_values(rows, ('worker', 'scheduler'), 'memory_bytes'))
        hourly.append(dict(hour=hour, cpu_average=cpu['sampled_percent_one_core']['average'],
                           memory_average_bytes=mem['average'], memory_p95_bytes=mem['p95'],
                           samples=len(rows)))
    before, after, review = load(before_path), load(after_path), load(review_path)
    if after.get('run_id') != manifest['run_id']:
        raise EvidenceError('Support snapshot belongs to a different run')
    if final and not deadline <= (parse_iso(after['checked_utc']) or 0) <= deadline+600:
        raise EvidenceError('A bounded post-cutoff support snapshot is required')
    cases_raw = [json.loads(line) for line in cases_path.read_text().splitlines() if line]
    names = [r.get('case') for r in cases_raw]
    if len(names) != len(CASE_NAMES) or set(names) != set(CASE_NAMES):
        raise EvidenceError('All eight distinct controlled-case receipts are required')
    cases = []
    for row in cases_raw:
        if not start <= row['started_at'] <= row['ended_at'] < deadline:
            raise EvidenceError('Controlled case falls outside the fixed observation')
        # No database names, private event identities, chat/message IDs or payloads.
        cases.append({k: row[k] for k in ('case', 'passed', 'started_at', 'ended_at',
            'api_attempts', 'acknowledged_parts', 'duplicate_resends', 'resends',
            'mongo_error_code', 'held_uncertain_parts', 'blocked_pending_parts',
            'acknowledged_messages', 'controlled_crossing', 'fallback_acknowledged',
            'forward_acknowledged', 'persisted', 'fixture_tasks_deleted', 'selected_live_reddit_candidate',
            'controlled_threshold', 'posts_recorded_sent', 'error_kind', 'error_code') if k in row})
    if (review.get('cases') != len(CASE_NAMES) or review.get('passed') != sum(r['passed'] for r in cases)
            or review.get('production_get_updates_calls') != 0):
        raise EvidenceError('Controlled receipts and their readback review disagree')
    identity = review.get('source_identity', {})
    if (not re.fullmatch(r'[a-f0-9]{40}', identity.get('verified_external_ci_head', ''))
            or not re.fullmatch(r'[a-f0-9]{64}', identity.get('artifact_sha256', ''))
            or not isinstance(identity.get('workflow_run'), int)):
        raise EvidenceError('Externally verified controlled-build identity is required')
    if all(r['passed'] for r in cases):
        for method, key in [('sendMessage','telegram_send_message_api_successes'),
                            ('forwardMessage','telegram_forward_message_api_successes')]:
            if sum(r['api_attempts'].get(method,0) for r in cases) != review.get(key):
                raise EvidenceError('Controlled acknowledgement totals disagree')
    natural_runs = []
    for row in after['anniversary_runs_in_window']:
        if any(not finite(row.get(k)) or row[k] < 0 for k in
               ('channels', 'due', 'completed', 'pending', 'uncertain_messages')):
            raise EvidenceError('Anniversary run counts are missing or invalid')
        natural_runs.append({k: row.get(k) for k in ('started_at', 'finished_at', 'status',
            'channels', 'due', 'completed', 'pending', 'uncertain_messages')})
    milestone_events = after['milestone_events_created_in_window']
    completed_in_window = sum(start <= (mongo_utc(r.get('completed_at')) or math.inf) < deadline
                              for r in milestone_events if r.get('complete'))
    warm_age = next((r.get('worker_age_seconds_at_start') for r in
                    read_records(directory/'notes.jsonl', {})
                    if r.get('event') == 'worker_already_running_at_window_start'), None)
    cpu_seconds = components['application']['cpu']['seconds']
    worker = [r['components']['worker'] for r in samples if r['components'].get('worker')]
    result = dict(schema=1, scope='Separate Go 48-hour support follow-up; no historical comparison or pooled windows',
        run_id=manifest['run_id'], campaign=manifest['campaign'], status=manifest['status'],
        final=final, started_at=start, deadline=deadline, observed_through=end,
        started_utc=iso(start), deadline_utc=iso(deadline), exposure_seconds=end-start,
        scheduled_seconds=172800, build=build_receipt(manifest),
        warm_worker_age_seconds_at_start=warm_age, source_changed=manifest.get('source_changed'),
        sample_count=len(samples), components=components, hourly=hourly, jobs=jobs,
        cpu_seconds_per_completed_job=cpu_seconds/jobs['completed'] if finite(cpu_seconds) and jobs['completed'] else None,
        cpu_seconds_per_successful_job=cpu_seconds/jobs['successful'] if finite(cpu_seconds) and jobs['successful'] else None,
        sampling_coverage_fraction=components['application']['cpu']['short_interval_coverage_seconds']/(end-start) if end>start else None,
        sampling_errors=len(sampling_errors), process_sampling_errors=len(process_errors),
        post_window_primary_reads=sum(finite(r.get('ts')) and r['ts']>deadline for r in samples_raw),
        foreign_event_records=foreign, processes=process_summary(processes, start, end),
        worker_fds=distribution([r.get('fds') for r in worker]),
        worker_threads=distribution([r.get('threads') for r in worker]),
        worker_established_connections=distribution([r.get('tcp_states', {}).get('ESTABLISHED', 0)
            for r in worker if r.get('unreadable_processes', 0) == 0]),
        queued_backlog=distribution([r['counts']['1']+r['counts']['5'] for r in queue
            if '1' in r.get('counts', {}) and '5' in r['counts']]),
        oldest_queued_seconds=distribution([r.get('oldest_wait_seconds') for r in queue]),
        temporary_file_bytes=distribution([r.get('temporary_files', {}).get('bytes') for r in queue]),
        temporary_file_count=distribution([r.get('temporary_files', {}).get('files') for r in queue]),
        natural_support={m: jobs['modules'].get(m) for m in SUPPORT_MODULES},
        anniversary=dict(runs=natural_runs, pending_events=after['anniversary_pending_events'],
            part_states=after['anniversary_part_states'], inherited_parts=holds(before, after)),
        milestones=dict(created_events=len(milestone_events), completed_inside_window=completed_in_window,
            incomplete_at_snapshot=sum(not r.get('complete') for r in milestone_events)),
        statistics=dict(timestamped_rows=after['statistics_persisted_in_window'],
            scope='Rows with document timestamps inside the window, observed at the stated snapshot time; timestamps are not MongoDB commit times.'),
        support_snapshot_utc=after['checked_utc'], controlled_cases=cases,
        controlled_build={k: review.get('source_identity', {}).get(k) for k in
            ('runtime_linker_label', 'verified_external_ci_head', 'workflow_run', 'artifact_sha256', 'note', 'additional_live_builds')},
        controlled_review={k: review.get(k) for k in ('cases', 'passed', 'telegram_send_message_api_successes',
            'telegram_forward_message_api_successes', 'production_get_updates_calls',
            'isolated_database_readback_verified', 'duplicate_resends', 'receiver_conflict_code', 'coverage_limits')},
        methods={k: METHODS[k] for k in ('cpu', 'memory', 'instrumentation', 'percentiles',
            'timing', 'cpu_per_job', 'coverage', 'processes', 'http', 'reliability')},
        qualifications=[
            'The worker was already running at launch. Job timings require paired in-window starts/ends; in-flight boundary jobs remain censored.',
            'Controlled live cases use a separately compiled, test-channel-routed package with an outbound guard and isolated MongoDB state. They do not prove natural production events occurred.',
            'The controlled milestone crossing uses a live current count and a controlled prior count/threshold. Text fallback and checkpoint/forward resume are checked separately from the additional live Reddit candidate case; inspect each outcome.',
            'The receiver index mismatch is reproduced in isolated MongoDB. Per-production-job error codes were not captured, so historical receiver failures are not individually attributed.',
            'The weekly production slot falls outside the fixed 48-hour window. The weekly delivery path is checked only in the controlled live case.',
            'Controlled cases and read-only reviews share the host, MongoDB service and bot quota. Their processes are outside worker/scheduler accounting; contention and database observation cost are retained.',
            'Current channel schedules differ from the earlier 24-hour experiment. The earlier report and all its evidence remain separate and unchanged.',
        ], source_receipts=receipts,
        supplemental_receipts={name: source_receipt(path) for name, path in
            [('support_before', before_path), ('support_after', after_path),
             ('controlled_cases', cases_path), ('controlled_review', review_path), ('campaign_ledger', ledger_path)]})
    result['methods']['http'] = ('Recorded Go request and consumed decoded response-body counters from observed job ends. '
        'Excludes TLS/framing and remote media downloads performed by Telegram; not total wire bandwidth.')
    result['methods']['reliability'] = ('Success means a successful recorded task end, not delivery to every channel. '
        'Telegram acknowledgements include posts, support messages and error notices from whole jobs. '
        'Per-event delivery needs its separate checkpoint evidence. Uncertain anniversary parts remain unresolved and held. '
        'Observed duplicate source/channel records do not constitute a direct audit of Telegram duplicates.')
    return result


def render(bundle, output):
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import pyplot as plt
    import textwrap

    ink, muted, blue, orange, grid = '#192E40', '#536778', '#245EA8', '#B55E25', '#DFE7EF'
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 11,
                         'text.color': ink, 'axes.labelcolor': muted,
                         'xtick.color': muted, 'ytick.color': muted})
    fig = plt.figure(figsize=(16, 20), dpi=300, facecolor='#F8FAFC')
    def text(x, y, body, size=11, color=ink, weight='normal'):
        fig.text(x, y, body, fontsize=size, color=color, weight=weight, va='top')
    def value(n, divisor=1):
        return f'{n/divisor:,.2f}' if finite(n) else 'N/A'
    def compact(n):
        return f'{n/1000:.1f}k' if n >= 10000 else f'{n:,}'
    def section(y, title):
        text(.055, y, title, 15, weight='bold')
    title = 'Go: two days of live support checks'
    if not bundle['final']:
        title = 'PRELIMINARY — Go live support run in progress'
    text(.055, .965, title, 25, weight='bold')
    a, b = (datetime.fromtimestamp(bundle[k], timezone.utc).strftime('%d %b %Y %H:%M:%S UTC')
            for k in ('started_at', 'deadline'))
    text(.055, .935, f'{a}  →  {b}  |  Fixed 48-hour observation', 11, muted)
    build = bundle['build']
    text(.055, .919, f"Application {build.get('version', 'unavailable')}  ·  {build.get('compiler', 'compiler unavailable')}  ·  "
         f"Worker already running for {value(bundle['warm_worker_age_seconds_at_start'], 3600)} hours at launch", 10, muted)
    jobs, review = bundle['jobs'], bundle['controlled_review']
    successes = jobs['successful']/jobs['completed']*100 if jobs['completed'] else 0
    for x, label, number in [(.055, 'Recorded job ends', compact(jobs['completed'])),
                             (.30, 'Job success', f'{successes:.1f}%'),
                             (.51, 'Production TG acknowledgements', compact(jobs['counters'].get('telegram_messages', 0))),
                             (.80, 'Controlled live checks', f"{review['passed']}/{review['cases']}")]:
        text(x, .897, number, 25, blue, 'bold'); text(x, .869, label, 10, muted)
    text(.055, .848, 'Acknowledgements include posts, support messages and error notices. Task success does not prove every channel succeeded.', 10, muted)
    section(.819, 'CPU and memory across the observation')
    hours = [r['hour']+.5 for r in bundle['hourly']]
    for bounds, key, label, chart_title, divisor, color in [([.085,.683,.855,.10], 'cpu_average', '% of one core', 'Application CPU', 1, blue),
            ([.085,.551,.855,.10], 'memory_average_bytes', 'MiB (includes cache)', 'Application memory', 1024**2, orange)]:
        ax = fig.add_axes(bounds, facecolor='white')
        values = [r[key]/divisor if finite(r[key]) else math.nan for r in bundle['hourly']]
        ax.plot(hours, values, color=color, linewidth=1.8, marker='o', markersize=2)
        ax.set_xlim(0,48); ax.set_ylim(bottom=0); ax.set_xticks([0,12,24,36,48])
        ax.set_xlabel('Hours since launch'); ax.set_ylabel(label, fontsize=10)
        ax.grid(axis='y', color=grid, linewidth=.6); ax.spines[['top','right']].set_visible(False)
        ax.set_title(chart_title+' · hourly average; gaps remain missing', fontsize=10, loc='left', color=muted)
    section(.515, 'Average, median and P95 describe the measured workload')
    app, mongo = bundle['components']['application'], bundle['components']['mongodb']
    rows = [('App CPU (% one core)', app['cpu']['sampled_percent_one_core'], 1),
            ('App memory (MiB)', app['memory_bytes'], 1024**2),
            ('MongoDB CPU (% one core)', mongo['cpu']['sampled_percent_one_core'], 1),
            ('MongoDB memory (MiB)', mongo['memory_bytes'], 1024**2),
            ('Job processing (seconds)', jobs['processing_seconds'], 1),
            ('Queue wait (seconds)', jobs['queue_wait_seconds'], 1)]
    ax = fig.add_axes([.055,.348,.89,.144]); ax.axis('off')
    table = ax.table(cellText=[[label]+[value(stats.get(k),d) for k in ('average','median','p95','maximum')]
                              for label,stats,d in rows],
                     colLabels=['Measurement','Average','Median','P95','Sample max'],
                     colWidths=[.40,.15,.15,.15,.15],cellLoc='right',bbox=[0,0,1,1])
    table.auto_set_font_size(False); table.set_fontsize(10)
    for (r,c),cell in table.get_celld().items():
        cell.set_edgecolor(grid);cell.set_linewidth(.5)
        cell.set_facecolor('#EAF0F7' if r==0 else 'white')
        if c==0:cell.set_text_props(ha='left')
        if r==0:cell.set_text_props(weight='bold',color=ink)
    coverage = bundle['sampling_coverage_fraction']
    text(.055,.334, f"Application coverage: {value(coverage*100 if finite(coverage) else None)}%  |  "
         f"{bundle['sample_count']:,} samples  |  {jobs['paired_executions']:,} paired job timings  |  "
         f"{jobs['starts_without_observed_end']:,} starts without an end  |  "
         f"{bundle['processes'].get('root_identity_changes', 'N/A')} worker identity changes", 9, muted)
    section(.310, 'Scheduled production support and controlled delivery evidence')
    names = {'tech_anniversary':'Anniversaries','tech_store_stat':'Statistics / milestones',
             'tech_weekly_radar':'Weekly report','tech_receiver':'Channel intake / receiver','tech_cleaner':'Cleanup'}
    controlled = {'tech_anniversary':'Delivery, dedup and uncertainty hold',
                  'tech_store_stat':'Crossing, Reddit selection, fallback and resume',
                  'tech_weekly_radar':'Summary and directory sent live',
                  'tech_receiver':'Direct intake passed; index conflict reproduced',
                  'tech_cleaner':'Isolated files/tasks cleaned; summary sent'}
    related = {'tech_anniversary': CASE_NAMES[1:3], 'tech_store_stat': (CASE_NAMES[3], CASE_NAMES[7]),
               'tech_weekly_radar': CASE_NAMES[4:5], 'tech_receiver': (CASE_NAMES[0], CASE_NAMES[5]),
               'tech_cleaner': CASE_NAMES[6:7]}
    passed = {r['case']: r['passed'] for r in bundle['controlled_cases']}
    text(.27,.291,'Production job outcomes',9,muted, 'bold')
    text(.56,.291,'Controlled test-channel checks',9,muted, 'bold')
    for index,module in enumerate(SUPPORT_MODULES):
        y=.278-index*.024
        r=bundle['natural_support'][module]
        outcome = f"{r['successful']}/{r['completed']} jobs succeeded" if r else 'No recorded completion in window'
        text(.055,y,names[module],10,weight='bold')
        text(.27,y,outcome,10)
        detail = controlled[module] if all(passed.get(c) for c in related[module]) else 'Controlled case failed; inspect receipt'
        text(.56,y,detail,9,muted)
    held = bundle['anniversary']['part_states'].get('uncertain',0)
    due = sum(r.get('due') or 0 for r in bundle['anniversary']['runs'])
    completed = sum(r.get('completed') or 0 for r in bundle['anniversary']['runs'])
    text(.055,.157, f"Natural anniversary sweeps: {due} due, {completed} events completed. "
         f"New milestone events: {bundle['milestones']['created_events']}; "
         f"{bundle['milestones']['completed_inside_window']} completed inside the window.", 10)
    stat_rows = sum(r.get('rows',0) for r in bundle['statistics']['timestamped_rows'])
    text(.055,.142, f"At review: {held} uncertain anniversary parts. "
         f"Stats rows timestamped in window: {compact(stat_rows)}. "
         f"Receiver index-conflict reproduction: MongoDB {review['receiver_conflict_code']}.",10,orange)
    note = ('Controlled cases use isolated records and a test-channel-routed build; production inbound polling remains outside those checks. Milestone crossing uses controlled inputs; the additional candidate case queries live Reddit listings. '
            'The weekly production slot is outside this window. Production failures and held deliveries remain visible. '
            'The worker was already running at launch; boundary jobs are censored. CPU uses valid intervals up to 10 seconds; P95 uses nearest rank. '
            'Memory includes file cache; sampled maxima are not lifetime kernel peaks. Shared MongoDB, host and bot-quota effects from observation and controlled checks remain included. '
            'This follow-up preserves the earlier 24-hour report and makes no new Rust-versus-Go speed claim.')
    text(.055,.120,'\n'.join(textwrap.wrap(note,145)),9,muted)
    text(.055,.035, 'Inspect exact counts, distributions, coverage and source hashes in support-summary.json beside this image.',9,muted)
    output.parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(output,dpi=300,facecolor=fig.get_facecolor(),metadata={'Title':title})
    plt.close(fig)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('directory','support-before','support-after','controlled-cases','controlled-review'):
        parser.add_argument('--'+flag,type=Path,required=True)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--inspect',action='store_true')
    args=parser.parse_args()
    bundle=analyze(args.directory,args.support_before,args.support_after,args.controlled_cases,args.controlled_review,final=not args.inspect)
    if args.inspect:
        print(json.dumps(bundle,indent=2,sort_keys=True));return
    if args.output is None:parser.error('--output is required for final export')
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'support-summary.json').write_text(json.dumps(bundle,indent=2,sort_keys=True)+'\n')
    render(bundle,args.output/'go-support-48h.png')
    receipt={p.name:source_receipt(p) for p in args.output.iterdir() if p.is_file() and p.name!='render-receipt.json'}
    (args.output/'render-receipt.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(run_id=bundle['run_id'],output=str(args.output),status='rendered_pending_visual_review'),indent=2))


if __name__=='__main__':
    main()
