from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest import mock

import mongomock
import pytest
from pymongo.errors import AutoReconnect
from telegram.error import BadRequest, Forbidden, RetryAfter, TimedOut

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'reddit2telegram'))
import supplier
import reporting_stuff
import utils
from utils import anniversaries as ann

with mock.patch('utils.tech.get_dev_channel', return_value=-1):
    from channels.tech_anniversary import app as job


@pytest.fixture
def sweep(monkeypatch, tmp_path):
    db = mongomock.MongoClient().db
    cron = tmp_path / 'own.cron'
    cron.write_text('MASK\tsubmodule_name\n55 11 * * *\tr_alpha\n55 11 * * *\tr_beta\n')
    sender = SimpleNamespace(
        settings=db.settings, urls=db.urls, stats=db.stats, t_channel=-1,
        config={'cron_file': str(cron), 'telegram': {'dev_chat': -1}},
        calls=[], errors={}, after_ack=None, on_message_sent=None,
    )
    db.channels.insert_many([
        {'submodule': 'r_alpha', 'channel': '@r_alpha'},
        {'submodule': 'r_beta', 'channel': '@r_beta'},
    ])
    db.urls.insert_many([
        {'channel': '@r_alpha', 'sent': True, 'ts': datetime(2019, 10, 17)},
        {'channel': '@r_beta', 'sent': True, 'ts': datetime(2020, 10, 17)},
    ])

    def send_text(text, **kwargs):
        error = sender.errors.get(sender.t_channel)
        if error is not None:
            raise error
        sender.calls.append((sender.t_channel, text, kwargs))
        if sender.on_message_sent is not None:
            sender.on_message_sent([len(sender.calls)])
        if sender.after_ack is not None:
            raise sender.after_ack
        return utils.SupplyResult.SUCCESSFULLY

    sender.send_text = send_text
    monkeypatch.setattr(ann, 'short_sleep', lambda: None)
    return sender, db, ann.AnniversaryAnnouncements(sender)


def event(db, channel='@r_alpha', year=2026):
    return db.settings.find_one({'kind': ann.EVENT_KIND, 'channel': channel, 'year': year})


def test_date_uses_successful_posts_and_survives_history_cleanup(sweep):
    sender, db, service = sweep
    db.urls.insert_many([
        {'channel': '@r_alpha', 'sent': False, 'ts': datetime(2017, 1, 1)},
        {'channel': '@r_alpha', 'sent': True},
        {'channel': '@r_alpha', 'sent': True, 'ts': 'invalid'},
    ])
    db.stats.insert_one({'channel': '@r_alpha', 'ts': datetime(2026, 1, 2)})
    assert service.birthday('@r_alpha') == date(2019, 10, 17)
    db.urls.delete_many({})
    assert service.birthday('@r_alpha') == date(2019, 10, 17)
    assert service.birthday('@r_nohistory') is None
    assert db.settings.find_one({'kind': ann.DATE_KIND})['source'] == 'first_sent_post'


def test_explicit_date_overrides_cached_default_and_invalid_date_is_rejected(sweep):
    _, db, service = sweep
    service.birthday('@r_alpha')
    assert service.birthday('@r_alpha', {'anniversary_date': '2015-05-12'}) == date(2015, 5, 12)
    assert service.birthday('@r_alpha') == date(2015, 5, 12)
    with pytest.raises(ValueError):
        service.birthday('@r_alpha', {'anniversary_date': 'not-a-date'})
    assert db.settings.find_one({'channel': '@r_alpha', 'kind': ann.DATE_KIND})['source'] == 'explicit'


def test_read_only_inventory_does_not_initialize_dates_or_delivery_records(sweep):
    _, db, service = sweep
    channels, skipped, errors = service.inventory(persist=False)
    assert channels == {'@r_alpha': date(2019, 10, 17), '@r_beta': date(2020, 10, 17)}
    assert skipped == errors == []
    assert db.settings.count_documents({}) == 0


def test_legacy_destination_is_read_without_executing_module(sweep, monkeypatch, tmp_path):
    sender, db, service = sweep
    module = tmp_path / 'r_legacy'
    module.mkdir()
    (module / 'app.py').write_text('raise AssertionError("Do not execute me")\nt_channel = "@r_legacy"\n')
    monkeypatch.setattr(ann, 'CHANNELS_DIR', tmp_path)
    Path(sender.config['cron_file']).write_text('MASK\tsubmodule_name\n55 11 * * *\tr_legacy\n')
    db.urls.insert_one({'channel': '@r_legacy', 'sent': True, 'ts': datetime(2018, 1, 1)})
    assert service.inventory(persist=False) == ({'@r_legacy': date(2018, 1, 1)}, [], [])
    assert db.settings.count_documents({}) == 0


@pytest.mark.parametrize('birthday,today,expected', [
    ('2019-10-17', '2026-10-17', 7),
    ('2019-10-17', '2026-10-18', None),
    ('2026-10-17', '2026-10-17', None),
    ('2027-10-17', '2026-10-17', None),
    ('2020-02-29', '2026-02-28', 6),
    ('2020-02-29', '2026-03-01', None),
    ('2020-02-29', '2028-02-28', None),
    ('2020-02-29', '2028-02-29', 8),
])
def test_anniversary_dates_including_leap_years(birthday, today, expected):
    assert ann.anniversary_age(birthday, today) == expected


def test_anniversary_date_normalizes_aware_timestamps_to_utc():
    observed = datetime(2019, 10, 18, 1, tzinfo=timezone(timedelta(hours=3)))
    assert ann.anniversary_age(observed, date(2026, 10, 17)) == 7


def test_inventory_isolates_missing_configuration_history_and_invalid_dates(sweep, monkeypatch):
    sender, db, service = sweep
    Path(sender.config['cron_file']).write_text(
        'MASK\tsubmodule_name\n' + ''.join('55 11 * * *\t{}\n'.format(name) for name in [
            'r_alpha', 'r_beta', 'r_missing', 'r_nourls', 'r_invalid', 'r_duplicate',
            'r_test', 'r_private', 'tech_anniversary',
        ]))
    db.channels.insert_many([
        {'submodule': 'r_nourls', 'channel': '@r_nourls'},
        {'submodule': 'r_invalid', 'channel': '@r_invalid', 'anniversary_date': 'bad'},
        {'submodule': 'r_duplicate', 'channel': '@R_ALPHA'},
        {'submodule': 'r_test', 'channel': '@r_channels_test'},
        {'submodule': 'r_private', 'channel': -123},
    ])
    monkeypatch.setattr(utils.channels_stuff, 'import_submodule', mock.Mock(side_effect=ValueError))
    channels, skipped, errors = service.inventory()
    assert set(channels) == {'@r_alpha', '@r_beta'}
    assert skipped == ['@r_nourls']
    assert {error['submodule'] for error in errors} == {'r_missing', 'r_invalid'}


def test_copy_promotes_featured_pair_first_and_splits_a_large_directory():
    others = ['@channel_' + str(i).zfill(23) for i in range(900)]
    messages = ann.announcement_messages('@birthday_channel', 7, others + [
        '@reddit2telegram', '@r_channels', '@r_channels_test', '@birthday_channel', others[0],
    ], date(2026, 10, 17))
    intro = messages[0]
    assert intro.index('@reddit2telegram') < intro.index('@r_channels') < intro.index('@birthday_channel')
    assert '7 years' in intro and '17 October 2026' in intro
    assert all(len(text.encode('utf-16-le')) // 2 < 4096 for text in messages)
    directory = '\n'.join(messages[1:])
    assert all(directory.count(handle) == 1 for handle in others)
    assert '@birthday_channel' not in directory and '@r_channels' not in directory
    assert all('More channels ·' in page for page in messages[1:])


def test_annual_event_is_unique_and_plan_is_frozen(sweep):
    _, db, service = sweep
    service.queue('@r_alpha', 7, date(2026, 10, 17), ['@r_alpha', '@r_beta'])
    planned = event(db)['deliveries']
    service.queue('@r_alpha', 7, date(2026, 11, 1), ['@changed_directory'])
    assert event(db)['deliveries'] == planned
    service.queue('@r_alpha', 8, date(2027, 10, 17), ['@r_beta'])
    assert db.settings.count_documents({'kind': ann.EVENT_KIND}) == 2


def test_repeated_run_does_not_repeat_sends_and_history_survives_task_cleaner(sweep):
    sender, db, service = sweep
    first = service.run(date(2026, 10, 17))
    assert first['status'] == 'success' and first['due'] == first['completed'] == 2
    sends = list(sender.calls)
    second = service.run(date(2026, 10, 17))
    assert second['status'] == 'success' and second['completed'] == 0
    assert sender.calls == sends
    db.tasks.delete_many({})
    assert db.settings.count_documents({'kind': ann.RUN_KIND}) == 2
    assert db.settings.count_documents({'kind': ann.EVENT_KIND, 'complete': True}) == 2


def test_definite_rejection_isolated_and_retries_only_unsent_parts_next_day(sweep):
    sender, db, service = sweep
    sender.errors['@r_alpha'] = Forbidden('not an administrator')
    first = service.run(date(2026, 10, 17))
    assert first['status'] == 'partial' and first['completed'] == 1
    assert event(db, '@r_beta')['complete']
    assert not event(db)['complete']
    sent_before = list(sender.calls)
    sender.errors.clear()
    second = service.run(date(2026, 10, 18))
    assert second['status'] == 'success' and second['due'] == 0 and second['completed'] == 1
    retried = sender.calls[len(sent_before):]
    assert retried and {destination for destination, *_ in retried} == {'@r_alpha'}
    assert all('17 October 2026' in text for _, text, _ in retried if 'family' in text)


def test_resume_after_a_directory_page_is_rejected_does_not_repeat_intro(sweep):
    sender, db, service = sweep
    service.acquire()
    service.queue('@r_alpha', 7, date(2026, 10, 17), ['@r_alpha', '@r_beta'])
    original = sender.send_text

    def reject_directory(text, **kwargs):
        if sender.t_channel == '@r_alpha' and 'More channels ·' in text:
            raise RetryAfter(30)
        return original(text, **kwargs)

    sender.send_text = reject_directory
    assert not service.deliver(event(db))
    sender.send_text = original
    before = len(sender.calls)
    assert service.deliver(event(db))
    assert len(sender.calls) == before + 1
    assert 'More channels ·' in sender.calls[-1][1]
    assert sum('family' in text for channel, text, _ in sender.calls if channel == '@r_alpha') == 1


@pytest.mark.parametrize('error', [TimedOut(), RuntimeError('lost response')])
def test_ambiguous_delivery_is_held_for_review_and_never_automatically_reposted(sweep, error):
    sender, db, service = sweep
    sender.errors['@r_alpha'] = error
    first = service.run(date(2026, 10, 17))
    assert first['uncertain_messages'] == 1
    assert event(db)['deliveries'][0]['state'] == 'uncertain'
    sender.errors.clear()
    second = service.run(date(2026, 10, 18))
    assert second['status'] == 'partial' and second['uncertain_messages'] == 1
    assert not any(channel == '@r_alpha' for channel, *_ in sender.calls)
    assert event(db, '@r_beta')['complete']


def test_process_interruption_does_not_repeat_a_potentially_sent_message(sweep):
    sender, db, service = sweep
    service.queue('@r_alpha', 7, date(2026, 10, 17), ['@r_beta'])
    doc = event(db)
    db.settings.update_one({'_id': doc['_id']}, {'$set': {'deliveries.0.state': 'sending'}})
    run = service.run(date(2026, 10, 18))
    assert run['status'] == 'partial' and run['uncertain_messages'] == 1
    assert not any(channel == '@r_alpha' for channel, *_ in sender.calls)
    assert event(db)['deliveries'][0]['state'] == 'uncertain'


def test_late_acknowledgment_is_not_overwritten_by_stale_recovery(sweep):
    _, db, service = sweep
    service.queue('@r_alpha', 7, date(2026, 10, 17), ['@r_beta'])
    service.acquire()
    stale = event(db)
    stale['deliveries'][0]['state'] = 'sending'
    db.settings.update_one({'_id': stale['_id']}, {'$set': {
        'deliveries.0.state': 'sent', 'deliveries.0.message_ids': [100],
    }})
    service.deliver(stale)
    assert event(db)['deliveries'][0]['state'] == 'sent'
    assert event(db)['deliveries'][0]['message_ids'] == [100]


def test_database_outage_after_telegram_ack_does_not_cause_a_duplicate(sweep, monkeypatch):
    sender, db, service = sweep
    update_one = db.settings.update_one

    def lose_ack(selector, update, *args, **kwargs):
        if any(key.endswith('.sent_at') for key in update.get('$set', {})):
            raise AutoReconnect('DB connection lost while persisting Telegram response')
        return update_one(selector, update, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(db.settings, 'update_one', lose_ack)
        run = service.run(date(2026, 10, 17))
    assert run['status'] == 'partial' and run['uncertain_messages'] == 2
    assert event(db)['deliveries'][0]['state'] == 'sending'
    service.run(date(2026, 10, 18))
    assert event(db)['deliveries'][0]['state'] == 'uncertain'
    assert sum(channel == '@r_alpha' for channel, *_ in sender.calls) == 1
    assert sum(channel == '@r_beta' for channel, *_ in sender.calls) == 1


def test_acknowledgment_is_saved_even_if_a_later_step_raises(sweep):
    sender, db, service = sweep
    sender.after_ack = RuntimeError('failure after acknowledgment')
    first = service.run(date(2026, 10, 17))
    assert first['status'] == 'partial'  # Later directory parts resume next sweep.
    assert first['uncertain_messages'] == 0
    before = len(sender.calls)
    sender.after_ack = None
    assert service.run(date(2026, 10, 18))['status'] == 'success'
    assert all('More channels ·' in text for _, text, _ in sender.calls[before:])
    assert all(part['message_ids'] for part in event(db)['deliveries'])


def test_non_acknowledged_success_does_not_mark_event_complete(sweep):
    sender, db, service = sweep
    sender.send_text = lambda *args, **kwargs: utils.SupplyResult.SUCCESSFULLY
    run = service.run(date(2026, 10, 17))
    assert run['status'] == 'partial' and run['uncertain_messages'] > 0
    assert not event(db)['complete']


def test_inactive_channel_is_not_sent_a_retry(sweep):
    sender, db, service = sweep
    service.queue('@r_inactive', 7, date(2026, 10, 17), ['@r_alpha'])
    run = service.run(date(2026, 10, 18))
    assert sender.calls == []
    assert run['pending'] == 1 and run['status'] == 'partial'


def test_main_channel_birthday_does_not_send_two_introductions_to_same_destination(sweep):
    _, db, service = sweep
    service.queue(ann.MAIN_CHANNEL, 7, date(2026, 10, 17), [ann.MAIN_CHANNEL, '@r_beta'])
    doc = event(db, ann.MAIN_CHANNEL)
    destinations = [part['destination'] for part in doc['deliveries']]
    assert destinations.count(ann.MAIN_CHANNEL) == 2  # One introduction and one directory page.
    assert destinations.count(ann.COMMUNITY) == 1


def test_overlap_is_recorded_and_expired_lease_cannot_be_renewed_or_released_by_old_owner(sweep):
    sender, db, first = sweep
    second = ann.AnniversaryAnnouncements(sender)
    assert first.acquire()
    assert second.run(date(2026, 10, 17))['status'] == 'skipped_overlap'
    assert not second.acquire()
    db.settings.update_one({'_id': ann.LOCK_ID}, {'$set': {'expires_at': datetime.min}})
    assert second.acquire()
    with pytest.raises(RuntimeError, match='lease expired'):
        first.renew()
    first.release()
    assert db.settings.find_one({'_id': ann.LOCK_ID})['owner'] == second.owner
    assert db.settings.find_one({'kind': ann.RUN_KIND})['status'] == 'skipped_overlap'


def test_fatal_sweep_failure_is_retained_and_lock_is_released(sweep, monkeypatch):
    _, db, service = sweep
    monkeypatch.setattr(service, 'inventory', mock.Mock(side_effect=OSError('cron missing')))
    with pytest.raises(OSError):
        service.run(date(2026, 10, 17))
    record = db.settings.find_one({'kind': ann.RUN_KIND})
    assert record['status'] == 'failed' and record['finished_at'] >= record['started_at']
    assert record['errors'] == [{'error_type': 'OSError'}]
    assert db.settings.find_one({'_id': ann.LOCK_ID})['expires_at'] == datetime.min


def test_next_owner_marks_an_interrupted_run_in_retained_history(sweep):
    sender, db, first = sweep
    first.acquire()
    db.settings.insert_one({'_id': 'previous-run', 'kind': ann.RUN_KIND,
                            'owner': first.owner, 'status': 'running', 'started_at': ann.utc_now()})
    db.settings.update_one({'_id': ann.LOCK_ID}, {'$set': {'expires_at': datetime.min}})
    second = ann.AnniversaryAnnouncements(sender)
    assert second.run(date(2026, 10, 18))['status'] == 'success'
    previous = db.settings.find_one({'_id': 'previous-run'})
    assert previous['status'] == 'interrupted'
    assert previous['errors'] == [{'error_type': 'InterruptedSweep'}]


def test_job_runs_without_reddit_and_test_mode_never_updates_production_ledger(sweep, monkeypatch):
    sender, db, _ = sweep
    sender.t_channel = '@r_channels_test'
    monkeypatch.setattr(supplier.utils.channels_stuff, 'import_submodule', lambda name: job)
    monkeypatch.setattr(supplier.utils, 'Reddit2TelegramSender', mock.MagicMock(
        return_value=mock.MagicMock(__enter__=lambda _: sender)))
    reddit = mock.Mock(side_effect=AssertionError('Anniversary job must not fetch Reddit'))
    monkeypatch.setattr(supplier, 'send_to_channel_from_subreddit', reddit)
    assert supplier.supply('tech_anniversary', sender.config, is_test=True) == utils.SupplyResult.STOP_THIS_SUPPLY
    assert sender.calls and {destination for destination, *_ in sender.calls} == {'@r_channels_test'}
    assert db.settings.count_documents({}) == 0
    reddit.assert_not_called()


def test_job_exposes_partial_delivery_as_failed_supply(sweep, monkeypatch):
    monkeypatch.setattr(ann, 'utc_now', lambda: datetime(2026, 10, 17))
    sender, _, service = sweep
    monkeypatch.setattr(job, 'AnniversaryAnnouncements', lambda _: service)
    sender.errors['@r_alpha'] = BadRequest('chat not found')
    with pytest.raises(RuntimeError, match='needs attention'):
        job.send_post(None, sender)


def test_queue_records_partial_supply_as_failure_even_if_error_reporting_fails(sweep, monkeypatch):
    monkeypatch.setattr(ann, 'utc_now', lambda: datetime(2026, 10, 17))
    import task_queue

    sender, db, service = sweep
    monkeypatch.setattr(job, 'AnniversaryAnnouncements', lambda _: service)
    monkeypatch.setattr(utils.channels_stuff, 'import_submodule', lambda name: job)
    monkeypatch.setattr(utils, 'Reddit2TelegramSender', mock.MagicMock(
        return_value=mock.MagicMock(__enter__=lambda _: sender)))
    monkeypatch.setattr(supplier, 'long_sleep', lambda *args: None)
    monkeypatch.setattr(reporting_stuff, 'client', None)
    monkeypatch.setattr(reporting_stuff, 'send_report_to_dev_chat', mock.Mock(side_effect=OSError))
    sender.errors['@r_alpha'] = Forbidden('not an administrator')
    task = db.tasks.insert_one({'status': task_queue.TaskStatus.NEW.value})
    task_queue.execute_task(db.tasks, task.inserted_id, task_queue.TASK_SUPPLY,
                            {'submodule_name': 'tech_anniversary', 'config': sender.config})
    assert db.tasks.find_one({'_id': task.inserted_id})['status'] == task_queue.TaskStatus.FAILED.value
    assert db.settings.find_one({'kind': ann.RUN_KIND})['status'] == 'partial'


def test_reporting_decorator_preserves_success_value_and_original_failure(monkeypatch):
    monkeypatch.setattr(reporting_stuff, 'client', None)
    monkeypatch.setattr(reporting_stuff, 'send_report_to_dev_chat', mock.Mock(side_effect=OSError))
    assert reporting_stuff.report_error(lambda: 'success')() == 'success'

    @reporting_stuff.report_error
    def broken_job():
        raise ValueError('original job failure')

    with pytest.raises(ValueError, match='original job failure'):
        broken_job()
