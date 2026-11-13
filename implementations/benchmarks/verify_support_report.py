"""Independent arithmetic on a private snapshot of the actual 48h observations."""
import argparse
from collections import Counter
from decimal import Decimal
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from support_report import analyze
from verify_report import check_stats, close, records, reference_stats


def verify(directory, before, after, cases, review, final=True):
    with tempfile.TemporaryDirectory(prefix='r2t-support-check-') as temporary:
        base = Path(temporary)
        target = base/'runs'/directory.name
        target.mkdir(parents=True)
        (base/'state').mkdir()
        shutil.copyfile(directory.parent.parent/'state/experiment.json', base/'state/experiment.json')
        for path in directory.iterdir():
            if path.is_file() and path.suffix in ('.json', '.jsonl'):
                shutil.copyfile(path, target/path.name)
        model = analyze(target,before,after,cases,review,final=final)
        start, end = model['started_at'], model['observed_through']
        assert model['deadline']-start == model['scheduled_seconds'] == 172800
        samples = [r for r in records(target/'samples.jsonl')
                   if 'components' in r and start <= r.get('ts',-1) <= end]
        assert len(samples) == model['sample_count']
        component_checks = {}
        for name, names in [('application',('worker','scheduler')),('worker',('worker',)),
                            ('scheduler',('scheduler',)),('mongodb',('mongodb',)),
                            ('combined',('worker','scheduler','mongodb'))]:
            for key in ('memory_bytes','rss_bytes','file_cache_bytes'):
                values = [sum(r['components'][n][key] for n in names) for r in samples
                          if all(r['components'].get(n) is not None and
                                 isinstance(r['components'][n].get(key),(float,int)) for n in names)]
                check_stats(model['components'][name][key], reference_stats(values))
            total, short_total, exposure = Decimal(0), Decimal(0), Decimal(0)
            rates=[]; intervals=missing=resets=long_gaps=nonpositive=0
            for left,right in zip(samples,samples[1:]):
                dt=right['ts']-left['ts']
                if dt<=0:
                    nonpositive+=1;continue
                if any(left['components'].get(n) is None or right['components'].get(n) is None for n in names):
                    missing+=1;continue
                changes=[right['components'][n]['cpu_usec']-left['components'][n]['cpu_usec'] for n in names]
                if any(v<0 for v in changes):
                    resets+=1;continue
                amount=Decimal(sum(changes))/Decimal(1000000)
                total+=amount;intervals+=1
                if dt<=10:
                    duration=Decimal(str(dt));short_total+=amount;exposure+=duration
                    rates.append(float(amount/duration*100))
                else:long_gaps+=1
            actual=model['components'][name]['cpu']
            close(actual['seconds'],float(total) if intervals else None)
            expected=reference_stats(rates)
            expected['average']=float(short_total/exposure*100) if exposure else None
            check_stats(actual['sampled_percent_one_core'],expected)
            assert actual['missing_component_intervals']==missing
            assert actual['counter_reset_intervals']==resets
            assert actual['long_gap_intervals']==long_gaps
            assert actual['nonpositive_intervals']==nonpositive
            component_checks[name]=dict(eligible_samples=len(samples),valid_cpu_intervals=intervals,
                                       short_cpu_intervals=len(rates),missing_component_intervals=missing)
        events=[r for r in records(target/'events.jsonl') if start<=r.get('ts',-1)<end
                and r.get('run_id')==model['run_id']]
        starts=[r for r in events if r.get('event')=='job_start']
        ends=[r for r in events if r.get('event')=='job_end']
        assert len(ends)==model['jobs']['completed']
        assert sum(r.get('status')=='success' for r in ends)==model['jobs']['successful']
        assert model['jobs']['successful']+model['jobs']['failed']==len(ends)
        assert sum(model['jobs']['errors'].values())==model['jobs']['failed']
        app_cpu=model['components']['application']['cpu']['seconds']
        close(model['cpu_seconds_per_completed_job'],app_cpu/len(ends) if app_cpu is not None and ends else None)
        successes=model['jobs']['successful']
        close(model['cpu_seconds_per_successful_job'],app_cpu/successes if app_cpu is not None and successes else None)
        totals=Counter()
        for row in ends:totals.update(row.get('counters',{}))
        assert dict(totals)==model['jobs']['counters']
        # Pair independent in-window execution records, consuming each start once.
        # Select closest duration only when an execution ID was repeated.
        unused={};paired=[]
        for row in starts:unused.setdefault((row['task_id'],row['module']),[]).append(row)
        for row in sorted(ends,key=lambda r:r['ts']):
            candidates=unused.get((row['task_id'],row['module']),[])
            possible=[(i,r) for i,r in enumerate(candidates) if r['ts']<=row['ts']]
            if possible:
                index,_=min(possible,key=lambda item:abs(row['ts']-item[1]['ts']-row.get('duration_seconds',0)))
                candidates.pop(index);paired.append(row)
        assert len(paired)==model['jobs']['paired_executions']
        check_stats(model['jobs']['processing_seconds'],reference_stats([r.get('duration_seconds') for r in paired]))
        check_stats(model['jobs']['queue_wait_seconds'],reference_stats([r.get('queue_wait_seconds') for r in paired]))
        for name,actual in model['natural_support'].items():
            subset=[r for r in ends if r.get('module')==name]
            coverage=model['natural_support_event_coverage'][name]
            beginnings=[r for r in starts if r.get('module')==name]
            assert coverage['started']==len(beginnings)
            assert coverage['completed']==len(subset)
            assert coverage['paired_executions']==sum(r.get('module')==name for r in paired)
            assert coverage['starts_without_observed_end']==len(beginnings)-coverage['paired_executions']
            assert coverage['orphan_end_records']==len(subset)-coverage['paired_executions']
            if not subset:assert actual is None
            else:
                assert actual['completed']==len(subset)
                assert actual['successful']==sum(r.get('status')=='success' for r in subset)
                assert actual['telegram_messages']==sum(r.get('counters',{}).get('telegram_messages',0) for r in subset)
        queue=[r for r in records(target/'queue.jsonl') if start<=r.get('ts',-1)<=end]
        check_stats(model['queued_backlog'],reference_stats([r['counts']['1']+r['counts']['5'] for r in queue
                    if '1' in r.get('counts',{}) and '5' in r['counts']]))
        for name,receipt in model['source_receipts'].items():
            if receipt['present']:assert hashlib.sha256((target/name).read_bytes()).hexdigest()==receipt['sha256']
        milestones=json.loads(after.read_text())['milestone_events_created_in_window']
        assert len(model['milestones']['events'])==len(milestones)
        for actual,raw in zip(model['milestones']['events'],milestones):
            for output_key,source_key in [('achievement','achievement'),('attempts','attempts'),
                ('source_message_checkpoint_count','message_ids_count'),
                ('forwarded_source_checkpoint_count','forwarded_ids_count')]:
                assert actual[output_key]==raw.get(source_key)
        anniversaries=json.loads(after.read_text()).get('anniversary_events_created_in_window',[])
        assert len(model['anniversary']['new_events'])==len(anniversaries)
        anniversary_acknowledgements=0
        for actual,raw in zip(model['anniversary']['new_events'],anniversaries):
            assert actual['parts']==len(raw['parts'])
            assert actual['sent_parts']==sum(p.get('state')=='sent' for p in raw['parts'])
            assert actual['complete_at_snapshot']==raw.get('complete')
            for part in raw['parts']:
                if part.get('state')!='sent' or part.get('sent_at') is None:continue
                sent=datetime.fromisoformat(part['sent_at'])
                if sent.tzinfo is None:sent=sent.replace(tzinfo=timezone.utc)
                if start<=sent.timestamp()<model['deadline']:
                    anniversary_acknowledgements+=part['message_id_count']
        assert model['anniversary']['new_delivery_parts_acknowledged_inside_window']==anniversary_acknowledgements
        return dict(run_id=model['run_id'],final=final,verified=True,
            measurement_status=model['status'],window_seconds=172800,
            components=component_checks,completed_jobs=len(ends),paired_executions=len(paired),
            checks=['All five component CPU cumulative totals and weighted mean/median/P95/min/max',
                    'All five component memory/RSS/file-cache mean/median/P95/min/max',
                    'Missing components, counter resets, long gaps and nonpositive intervals',
                    'Job outcomes, error totals and all recorded counters including acknowledgements and 429 responses',
                    'Execution-paired processing and queue timing distributions',
                    'All five scheduled support-module starts, completions, censored counts, outcomes and acknowledgements',
                    'Curated natural milestone thresholds, attempts and delivery/forward checkpoints',
                    'New natural anniversary events and persisted part checkpoint counts',
                    'Queue-backlog distribution, exact bounds and frozen raw-file hashes'],
            source_receipts=model['source_receipts'],
            scope='Actual live observations only. A temporary private copy stabilizes arithmetic; it creates no app work, replay or synthetic traffic.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('directory','support-before','support-after','controlled-cases','controlled-review','receipt'):
        parser.add_argument('--'+flag,type=Path,required=True)
    parser.add_argument('--allow-running',action='store_true')
    args=parser.parse_args()
    result=verify(args.directory,args.support_before,args.support_after,args.controlled_cases,args.controlled_review,final=not args.allow_running)
    args.receipt.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k:result[k] for k in ('run_id','final','verified','measurement_status','completed_jobs','paired_executions')},indent=2))
