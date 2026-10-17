from datetime import datetime, timedelta
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest import mock

import mongomock
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'reddit2telegram'))
import supplier
import utils
from utils.achievements import AchievementAnnouncements, EVENT_SETTING, LOCK_ID, SETTING_NAME
from utils import promotion

with mock.patch('utils.tech.get_dev_channel', return_value=-1):
    from channels.tech_store_stat import app as job


@pytest.fixture
def delivery(monkeypatch):
    settings = mongomock.MongoClient().db.settings
    settings.create_index('setting', unique=True)
    config = {'telegram': {'token': '123:offline-test'}}
    service = AchievementAnnouncements(settings, config)
    assert service.acquire()
    calls = SimpleNamespace(posts=[], forwards=[], fail_post=False, fail_forward=False,
                            fail_after_post=False, no_candidates=False)

    class Sender:
        def __init__(self, channel, supplied_config):
            assert supplied_config is config
            self.t_channel = channel
            self.on_message_sent = None

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def send_text(self, text):
            if calls.fail_post:
                raise RuntimeError('Telegram unavailable')
            calls.posts.append(text)
            self.on_message_sent([len(calls.posts)])
            if calls.fail_after_post:
                raise RuntimeError('Later posting step failed')
            return utils.SupplyResult.SUCCESSFULLY

        def forward_message(self, **kwargs):
            if calls.fail_forward:
                raise RuntimeError('Destination temporarily unavailable')
            calls.forwards.append(kwargs)

    def supply(**kwargs):
        if calls.no_candidates:
            return False
        with Sender(kwargs['channel_to_post'], kwargs['config']) as sender:
            return kwargs['how_to_post'](None, sender, **kwargs)

    monkeypatch.setattr(utils, 'Reddit2TelegramSender', Sender)
    monkeypatch.setattr(supplier, 'send_to_channel_from_subreddit', supply)
    monkeypatch.setattr('utils.achievements.make_nice_submission',
                        lambda submission, sender, **kwargs: sender.send_text(kwargs['announcement_heading']))
    monkeypatch.setattr(utils.channels_stuff, 'import_submodule',
                        lambda name: SimpleNamespace(subreddit='space', t_channel='@' + name))
    return service, calls


def queue(service, channel='@r_space', achievement=100):
    service.queue(channel.lstrip('@'), channel, achievement)
    return service.settings.find_one({'kind': EVENT_SETTING, 'channel': channel.lower(),
                                      'achievement': achievement})


def test_completion_requires_public_acknowledgment(delivery):
    service, calls = delivery
    event = queue(service)
    calls.fail_post = True
    with pytest.raises(RuntimeError):
        service.deliver(event)
    assert service.settings.find_one({'setting': SETTING_NAME}) is None
    assert list(service.pending())[0]['message_ids'] == []
    calls.fail_post = False
    service.deliver(list(service.pending())[0])
    assert list(service.pending()) == []
    assert len(calls.posts) == len(calls.forwards) == 1
    assert '@r_space' in calls.posts[0] and '100 subscribers' in calls.posts[0]
    assert service.settings.find_one({'setting': SETTING_NAME})['channels'] == {'@r_space': [100]}


def test_forward_failure_retries_same_message_without_reposting(delivery):
    service, calls = delivery
    event = queue(service)
    calls.fail_forward = True
    with pytest.raises(RuntimeError):
        service.deliver(event)
    assert len(calls.posts) == 1
    calls.fail_forward = False
    service.deliver(list(service.pending())[0])
    assert len(calls.posts) == 1
    assert calls.forwards == [dict(chat_id='@r_space', from_chat_id='@reddit2telegram', message_id=1)]
    assert list(service.pending()) == []


def test_partial_post_or_history_failure_does_not_repost(delivery):
    service, calls = delivery
    calls.fail_after_post = True
    service.deliver(queue(service))
    assert len(calls.posts) == len(calls.forwards) == 1
    assert list(service.pending()) == []


def test_partial_gallery_stops_candidate_search(delivery, monkeypatch):
    service, calls = delivery
    observed = []
    def partial_gallery(submission, sender, **kwargs):
        sender.send_text(kwargs['announcement_heading'])
        return utils.SupplyResult.SKIP_FOR_NOW
    original_supply = supplier.send_to_channel_from_subreddit
    def supply(**kwargs):
        observed.append(original_supply(**kwargs))
    monkeypatch.setattr('utils.achievements.make_nice_submission', partial_gallery)
    monkeypatch.setattr(supplier, 'send_to_channel_from_subreddit', supply)
    service.deliver(queue(service))
    assert observed == [utils.SupplyResult.STOP_THIS_SUPPLY]
    assert len(calls.posts) == len(calls.forwards) == 1


def test_no_candidates_falls_back_to_explicit_milestone_text(delivery):
    service, calls = delivery
    calls.no_candidates = True
    service.deliver(queue(service))
    assert calls.posts == ['🏆 Great achievement!\n@r_space\n💪 Milestone of 100 subscribers.']
    assert len(calls.forwards) == 1


def test_reddit_outage_still_announces_known_milestone(delivery, monkeypatch):
    service, calls = delivery
    monkeypatch.setattr(supplier, 'send_to_channel_from_subreddit',
                        mock.Mock(side_effect=RuntimeError('Reddit unavailable')))
    service.deliver(queue(service))
    assert len(calls.posts) == len(calls.forwards) == 1
    assert '100 subscribers' in calls.posts[0]
    assert list(service.pending()) == []


def test_atomic_history_updates_preserve_other_channels(delivery):
    service, calls = delivery
    events = [queue(service, '@r_space'), queue(service, '@r_moon')]
    for event in events:
        service.deliver(event)
    assert service.settings.find_one({'setting': SETTING_NAME})['channels'] == {
        '@r_space': [100], '@r_moon': [100]}
    assert len(calls.posts) == 2


def test_existing_history_and_case_normalization_prevent_duplicates(delivery):
    service, calls = delivery
    service.settings.insert_one({'setting': SETTING_NAME, 'channels': {'@r_space': [100]}})
    assert queue(service, '@R_SPACE') is None
    first = queue(service, achievement=200)
    assert queue(service, achievement=200)['_id'] == first['_id']
    assert len(list(service.pending())) == 1
    service.deliver(first)
    assert service.settings.find_one({'setting': SETTING_NAME})['channels']['@r_space'] == [100, 200]


def test_forward_each_part_and_resume_after_partial_forward(delivery):
    service, calls = delivery
    event = queue(service)
    service.settings.update_one({'_id': event['_id']}, {
        '$set': {'message_ids': [11, 12, 13], 'forwarded_ids': [11]}})
    service.deliver(list(service.pending())[0])
    assert [item['message_id'] for item in calls.forwards] == [12, 13]
    assert calls.posts == []


def test_announcements_channel_is_not_forwarded_to_itself(delivery):
    service, calls = delivery
    service.deliver(queue(service, '@reddit2telegram'))
    assert len(calls.posts) == 1
    assert calls.forwards == []


def test_lease_prevents_overlap_and_stale_owner_writes(delivery):
    first, _ = delivery
    second = AchievementAnnouncements(first.settings, first.config)
    assert not second.acquire()
    first.settings.update_one({'_id': LOCK_ID}, {'$set': {'expires_at': datetime.utcnow() - timedelta(seconds=1)}})
    with pytest.raises(RuntimeError, match='lease expired'):
        first.renew()
    assert second.acquire()
    first.release()
    second.renew()
    with pytest.raises(RuntimeError, match='lease expired'):
        first.deliver(queue(second))
    second.release()
    assert first.acquire()


@pytest.fixture
def sweep(delivery, monkeypatch):
    service, calls = delivery
    service.release()
    database = service.settings.database
    reports = []
    counts = {'@r_space': 100}
    sender = SimpleNamespace(settings=service.settings, config=service.config, stats=database.stats,
                             send_text=lambda text, **kwargs: reports.append(text),
                             get_chat_members_count=lambda chat_id: counts[chat_id])
    monkeypatch.setattr(job, 'get_all_public_submodules', lambda: ['r_space'])
    monkeypatch.setattr(job, 'get_admins_list', lambda *args: [])
    monkeypatch.setattr(job, 'short_sleep', lambda *args: None)
    return sender, counts, reports, service, calls


def add_count(sender, count, seconds_ago=1, channel='@r_space'):
    sender.stats.insert_one({'channel': channel, 'members_cnt': count,
                             'ts': datetime.utcnow() - timedelta(seconds=seconds_ago)})


def test_sweep_retries_failed_milestone_after_count_advances(sweep):
    sender, counts, reports, service, calls = sweep
    add_count(sender, 99)
    calls.fail_post = True
    assert job.send_post(None, sender) == utils.SupplyResult.STOP_THIS_SUPPLY
    assert sender.stats.find_one({'members_cnt': 100})
    assert len(list(service.pending())) == 1
    assert list(service.pending())[0]['attempts'] == 1
    assert list(service.pending())[0]['last_error_type'] == 'RuntimeError'
    calls.fail_post = False
    counts['@r_space'] = 101
    job.send_post(None, sender)
    assert len(calls.posts) == 1 and '100 subscribers' in calls.posts[0]
    assert list(service.pending()) == []


def test_sweep_skips_when_another_worker_holds_lease(sweep):
    sender, counts, reports, service, calls = sweep
    assert service.acquire()
    job.send_post(None, sender)
    assert sender.stats.count_documents({}) == 0
    assert calls.posts == reports == []


def test_sweep_releases_lease_after_unexpected_failure(sweep, monkeypatch):
    sender, counts, reports, service, calls = sweep
    monkeypatch.setattr(job, 'get_all_public_submodules', mock.Mock(side_effect=RuntimeError('Invalid cron')))
    with pytest.raises(RuntimeError):
        job.send_post(None, sender)
    assert service.acquire()


@pytest.mark.parametrize('previous', [None, 0])
def test_new_and_zero_member_channels_do_not_crash(sweep, previous):
    sender, counts, reports, service, calls = sweep
    if previous is not None:
        add_count(sender, previous)
    job.send_post(None, sender)
    assert sender.stats.count_documents({'members_cnt': 100}) == 1
    assert any('regular bypass results' in report for report in reports)
    assert len(calls.posts) == (6 if previous == 0 else 0)


def test_failed_snapshot_does_not_hide_last_valid_count(sweep):
    sender, counts, reports, service, calls = sweep
    add_count(sender, 99, seconds_ago=10)
    sender.stats.insert_one({'channel': '@r_space', 'ts': datetime.utcnow()})
    job.send_post(None, sender)
    assert len(calls.posts) == 1


def test_empty_sweep_still_retries_pending_events(sweep, monkeypatch):
    sender, counts, reports, service, calls = sweep
    queue(service)
    monkeypatch.setattr(job, 'get_all_public_submodules', lambda: [])
    job.send_post(None, sender)
    assert len(calls.posts) == 1
    assert any('Active channels: 0' in report for report in reports)


def test_one_broken_channel_and_status_reports_do_not_abort_sweep(sweep, monkeypatch):
    sender, counts, reports, service, calls = sweep
    add_count(sender, 99)
    monkeypatch.setattr(job, 'get_all_public_submodules', lambda: ['broken', 'r_space'])
    def load(name):
        if name == 'broken':
            raise ValueError('invalid channel')
        return SimpleNamespace(subreddit='space', t_channel='@r_space')
    monkeypatch.setattr(utils.channels_stuff, 'import_submodule', load)
    sender.send_text = mock.Mock(side_effect=RuntimeError('Dev chat unavailable'))
    monkeypatch.setattr(job, 'get_admins_list', mock.Mock(side_effect=RuntimeError('Not an admin')))
    job.send_post(None, sender)
    assert len(calls.posts) == 1
    assert sender.stats.find_one({'members_cnt': 100})


def test_queue_failure_does_not_advance_subscriber_checkpoint(sweep, monkeypatch):
    sender, counts, reports, service, calls = sweep
    add_count(sender, 99)
    monkeypatch.setattr(AchievementAnnouncements, 'queue', mock.Mock(side_effect=RuntimeError('DB unavailable')))
    job.send_post(None, sender)
    assert not sender.stats.find_one({'members_cnt': 100})


def test_maintenance_supply_does_not_fetch_reddit_or_randomly_skip(monkeypatch):
    module = SimpleNamespace(t_channel=-1, requires_submission=False,
                             send_post=mock.Mock(return_value=utils.SupplyResult.STOP_THIS_SUPPLY))
    monkeypatch.setattr(utils.channels_stuff, 'import_submodule', lambda name: module)
    monkeypatch.setattr(supplier, 'long_sleep', lambda *args: None)
    with mock.patch.object(utils, 'Reddit2TelegramSender') as sender, mock.patch.object(
        supplier, 'send_to_channel_from_subreddit') as reddit, mock.patch.object(
        supplier, 'no_chance_to_post_due_to_errors_cnt') as skip:
        supplier.supply('tech_store_stat', {})
    module.send_post.assert_called_once_with(None, sender.return_value.__enter__.return_value)
    reddit.assert_not_called()
    skip.assert_not_called()


def test_sender_reports_exact_ids_for_text_and_media_groups():
    sender = utils.Reddit2TelegramSender.__new__(utils.Reddit2TelegramSender)
    sender._run_async = mock.Mock(side_effect=[SimpleNamespace(message_id=7),
                                             (SimpleNamespace(message_id=8), SimpleNamespace(message_id=9))])
    sender.on_message_sent = mock.Mock()
    sender._send_message('text coroutine')
    sender._send_message('media coroutine')
    assert sender.on_message_sent.call_args_list == [mock.call([7]), mock.call([8, 9])]


def test_promotion_heading_precedes_content_for_every_format(monkeypatch):
    monkeypatch.setattr(promotion, 'get_tags', lambda name: ['#space'])
    monkeypatch.setattr(promotion, 'what_channel', lambda name: '@r_space')
    sender = SimpleNamespace(send_simple=mock.Mock(return_value=utils.SupplyResult.SUCCESSFULLY))
    submission = SimpleNamespace(title='A very long title', created_utc=0)
    promotion.make_nice_submission(submission, sender, 'r_space', announcement_heading='Milestone\n')
    kwargs = sender.send_simple.call_args.kwargs
    assert kwargs['announcement_heading'] == 'Milestone\n'
    for kind in ['text', 'other', 'album', 'gif', 'img', 'video', 'gallery']:
        assert kwargs[kind].startswith('{announcement_heading}')


def test_queued_channel_remains_correct_after_configuration_changes(monkeypatch):
    monkeypatch.setattr(promotion, 'get_tags', lambda name: [])
    monkeypatch.setattr(promotion, 'what_channel', lambda name: '@renamed_channel')
    sender = SimpleNamespace(send_simple=mock.Mock(return_value=utils.SupplyResult.SUCCESSFULLY))
    promotion.make_nice_submission(SimpleNamespace(title='Title', created_utc=0), sender,
                                   'r_space', channel_to_promote='@r_space')
    assert sender.send_simple.call_args.kwargs['channel_to_promote'] == '@r_space'
