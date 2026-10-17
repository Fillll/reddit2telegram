"""Stable anniversary dates and resumable, annually unique text announcements.

All records live in settings, independently of the hourly task queue cleaner.
Telegram has no idempotency key: an interrupted/ambiguous send is held for review
instead of being automatically resent. Explicit API rejections can be retried.
"""

import ast
import calendar
import csv
from datetime import date, datetime, time, timedelta, timezone
from html import escape
import logging
from pathlib import Path
import re
from uuid import uuid4

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from telegram.error import BadRequest, ChatMigrated, Forbidden, RetryAfter

from utils import SupplyResult
from utils.tech import short_sleep


MAIN_CHANNEL = '@reddit2telegram'
COMMUNITY = '@r_channels'
DATE_KIND = 'r2t_anniversary_date'
EVENT_KIND = 'r2t_anniversary_delivery'
RUN_KIND = 'r2t_anniversary_run'
LOCK_ID = 'r2t_anniversary_sweep_lock'
LEASE = timedelta(hours=2)
HANDLE = re.compile(r'^@[a-zA-Z][a-zA-Z0-9_]{4,31}$')
EXCLUDED = {COMMUNITY, '@r_channels_test'}
CHANNELS_DIR = Path(__file__).resolve().parent.parent / 'channels'
logger = logging.getLogger(__name__)


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_date(value):
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc)
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def anniversary_age(birthday, today):
    birthday, today = utc_date(birthday), utc_date(today)
    month, day = birthday.month, birthday.day
    if (month, day) == (2, 29) and not calendar.isleap(today.year):
        day = 28
    years = today.year - birthday.year
    return years if (today.month, today.day) == (month, day) and years > 0 else None


def local_channel(module):
    # Legacy custom modules may have no DB document. Read their literal handle
    # without executing import-time promotion selection or other side effects.
    tree = ast.parse((CHANNELS_DIR / module / 'app.py').read_text())
    for statement in tree.body:
        if isinstance(statement, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == 't_channel'
                for target in statement.targets):
            return ast.literal_eval(statement.value)
    raise ValueError('No literal public channel destination')


def announcement_messages(channel, years, channels, celebrated_on=None):
    """Freeze a deterministic directory into single Telegram-sized messages."""
    plural = '' if years == 1 else 's'
    introduction = (
        '🌍 <b>Discover the Reddit2Telegram family</b>\n\n'
        '📣 @reddit2telegram — our main channel for discovering posts and channels '
        'from across the network.\n\n'
        '💬 @r_channels — join the community, find new channels, ask questions, '
        'and suggest your next favorite.\n\n'
        '🎂 <b>Celebrating {channel}: {years} year{plural} together!</b>\n'
        '{date_label}'
        'Thank you for reading, sharing, and being part of the community. '
        'Here’s to another year of great discoveries!'
    ).format(channel=escape(channel), years=years, plural=plural,
             date_label=('📅 {}\n'.format(celebrated_on.strftime('%d %B %Y'))
                         if celebrated_on is not None else ''))
    others = sorted({name.lower() for name in channels}
                    - {channel.lower(), MAIN_CHANNEL, COMMUNITY, '@r_channels_test'})
    if not others:
        return [introduction]
    introduction += '\n\n🧭 Explore more of our channels in the directory below.'
    pages, lines = [], []
    for number, name in enumerate(others, 1):
        line = '{}. {}'.format(number, escape(name))
        # Count UTF-16 units and reserve room for the page heading. Keeping each
        # call below 4096 avoids sender.send_text's untracked automatic splitting.
        candidate = '\n'.join(lines + [line])
        if lines and (len(lines) == 100 or len(candidate.encode('utf-16-le')) // 2 > 3400):
            pages.append('\n'.join(lines))
            lines = []
        lines.append(line)
    if lines:
        pages.append('\n'.join(lines))
    return [introduction] + [
        '🧭 <b>More channels · {}/{}</b>\n\n{}'.format(i, len(pages), page)
        for i, page in enumerate(pages, 1)
    ]


class AnniversaryAnnouncements:
    def __init__(self, sender):
        self.sender = sender
        self.settings = sender.settings
        self.owner = uuid4().hex
        self.previous_owner = None

    def acquire(self):
        try:
            self.settings.update_one(
                {'_id': LOCK_ID}, {'$setOnInsert': {
                    'setting': LOCK_ID, 'expires_at': datetime.min,
                }}, upsert=True,
            )
        except DuplicateKeyError:
            pass
        now = utc_now()
        previous = self.settings.find_one_and_update(
            {'_id': LOCK_ID, 'expires_at': {'$lte': now}},
            {'$set': {'owner': self.owner, 'expires_at': now + LEASE}},
            return_document=ReturnDocument.BEFORE,
        )
        self.previous_owner = previous.get('owner') if previous is not None else None
        return previous is not None

    def renew(self):
        now = utc_now()
        result = self.settings.update_one(
            {'_id': LOCK_ID, 'owner': self.owner, 'expires_at': {'$gt': now}},
            {'$set': {'expires_at': now + LEASE}},
        )
        if not result.matched_count:
            raise RuntimeError('Anniversary sweep lease expired or changed owner')

    def release(self):
        self.settings.update_one({'_id': LOCK_ID, 'owner': self.owner},
                                 {'$set': {'expires_at': datetime.min}})

    def birthday(self, channel, channel_doc=None, persist=True):
        selector = {'_id': '{}:{}'.format(DATE_KIND, channel)}
        cached = self.settings.find_one(selector)
        explicit = (channel_doc or {}).get('anniversary_date')
        if explicit is not None:
            birthday, source = utc_date(explicit), 'explicit'
        elif cached is not None:
            return utc_date(cached['date'])
        else:
            first_post = self.sender.urls.find_one(
                {'channel': channel, 'sent': True, 'ts': {'$type': 'date'}},
                sort=[('ts', 1)], projection={'ts': 1},
            )
            if first_post is None:
                return None
            birthday, source = utc_date(first_post['ts']), 'first_sent_post'
        if persist:
            values = {'setting': selector['_id'], 'kind': DATE_KIND, 'channel': channel,
                      'date': datetime.combine(birthday, time()), 'source': source}
            # Automatic dates are written only once; explicit operator overrides
            # deliberately replace the cached default without clearing delivery history.
            update = '$set' if explicit is not None else '$setOnInsert'
            self.settings.update_one(selector, {update: values}, upsert=True)
        return birthday

    def inventory(self, persist=True, heartbeat=None):
        channels, skipped, errors = {}, [], []
        with open(self.sender.config['cron_file']) as cron_file:
            modules = sorted({row['submodule_name'] for row in csv.DictReader(cron_file, delimiter='\t')
                              if not row['submodule_name'].startswith('tech_')})
        for module in modules:
            if heartbeat is not None:
                heartbeat()
            try:
                # Database-backed channels need no module imports or promotion
                # selection side effects simply to discover their handle/date.
                doc = self.sender.urls.database['channels'].find_one({'submodule': module})
                channel = doc['channel'] if doc else local_channel(module)
                if not isinstance(channel, str) or not HANDLE.fullmatch(channel):
                    continue
                channel = channel.lower()
                if channel in EXCLUDED or channel in channels:
                    continue
                birthday = self.birthday(channel, doc, persist=persist)
                if birthday is None:
                    skipped.append(channel)
                    logger.warning('Anniversary skipped: %s has no successful posting history', channel)
                    continue
                channels[channel] = birthday
            except Exception as exc:
                errors.append({'submodule': module, 'error_type': type(exc).__name__})
                logger.warning('Could not inspect anniversary channel %s (%s)', module, type(exc).__name__)
        return channels, skipped, errors

    def queue(self, channel, years, today, channels):
        event_id = '{}:{}:{}'.format(EVENT_KIND, channel, today.year)
        birthday_notice = ('🎂 <b>Celebrating {channel}: {years} year{plural} together!</b>\n'
                           '📅 {anniversary}\n\n'
                           'Discover this channel and more in our main feed @reddit2telegram.\n'
                           'Join @r_channels to explore the network and meet the community.').format(
                               channel=escape(channel), years=years, plural='' if years == 1 else 's',
                               anniversary=today.strftime('%d %B %Y'))
        deliveries = [{'destination': channel, 'text': text, 'state': 'pending'}
                      for text in announcement_messages(channel, years, channels, today)]
        destinations = {str(channel).lower()}
        for destination in [MAIN_CHANNEL, COMMUNITY, self.sender.config['telegram']['dev_chat']]:
            if str(destination).lower() in destinations:
                continue
            destinations.add(str(destination).lower())
            deliveries.append({'destination': destination, 'text': birthday_notice, 'state': 'pending'})
        self.settings.update_one({'_id': event_id}, {'$setOnInsert': {
            'setting': event_id, 'kind': EVENT_KIND, 'channel': channel, 'year': today.year,
            'years': years, 'anniversary': today.isoformat(), 'created_at': utc_now(),
            'complete': False, 'deliveries': deliveries,
        }}, upsert=True)

    def deliver(self, event):
        blocked = set()
        for index, delivery in enumerate(event['deliveries']):
            self.renew()
            destination = delivery['destination']
            path = 'deliveries.{}'.format(index)
            selector = {'_id': event['_id']}
            if delivery['state'] == 'sent' or destination in blocked:
                continue
            if delivery['state'] in ('sending', 'uncertain'):
                # A process may have died after Telegram accepted a request.
                self.settings.update_one(
                    {**selector, path + '.state': 'sending'},
                    {'$set': {path + '.state': 'uncertain'}},
                )
                blocked.add(destination)
                continue
            attempt = uuid4().hex
            claimed = self.settings.update_one(
                {**selector, path + '.state': 'pending'},
                {'$set': {path + '.state': 'sending', path + '.attempt': attempt,
                          path + '.attempted_at': utc_now()},
                 '$inc': {path + '.attempts': 1}},
            )
            if not claimed.matched_count:
                blocked.add(destination)
                continue
            attempt_selector = {**selector, path + '.attempt': attempt}
            acknowledged = []

            def remember(ids):
                acknowledged.extend(ids)
                result = self.settings.update_one(attempt_selector, {'$set': {
                    path + '.state': 'sent', path + '.message_ids': list(acknowledged),
                    path + '.sent_at': utc_now(),
                }})
                if not result.matched_count:
                    raise RuntimeError('Anniversary delivery attempt changed before acknowledgment')

            old_channel = self.sender.t_channel
            old_callback = getattr(self.sender, 'on_message_sent', None)
            try:
                self.sender.t_channel = destination
                self.sender.on_message_sent = remember
                result = self.sender.send_text(delivery['text'], parse_mode='HTML',
                                               disable_web_page_preview=True)
                if result != SupplyResult.SUCCESSFULLY or not acknowledged:
                    raise RuntimeError('Anniversary message was not acknowledged')
            except Exception as exc:
                # Definite Telegram API rejection is safe to retry. All other
                # failures may have accepted the message before losing the reply.
                state = 'pending' if isinstance(exc, (BadRequest, ChatMigrated, Forbidden, RetryAfter)) else 'uncertain'
                if acknowledged:
                    remember([])
                else:
                    self.settings.update_one(attempt_selector, {'$set': {
                        path + '.state': state, path + '.last_error_type': type(exc).__name__,
                    }})
                blocked.add(destination)
                logger.warning('Anniversary delivery needs attention: %s to %s (%s)',
                               event['_id'], destination, type(exc).__name__)
            finally:
                self.sender.t_channel = old_channel
                self.sender.on_message_sent = old_callback
            short_sleep()
        current = self.settings.find_one({'_id': event['_id']})
        complete = all(part['state'] == 'sent' for part in current['deliveries'])
        self.settings.update_one({'_id': event['_id']}, {'$set': {
            'complete': complete, 'updated_at': utc_now(),
        }})
        return complete

    def run(self, today=None):
        today = utc_date(today or utc_now())
        run_id = '{}:{}'.format(RUN_KIND, uuid4().hex)
        run = {'_id': run_id, 'kind': RUN_KIND, 'setting': run_id, 'owner': self.owner,
               'date': today.isoformat(), 'started_at': utc_now(), 'status': 'running',
               'channels': 0, 'due': 0, 'completed': 0, 'pending': 0, 'uncertain_messages': 0,
               'skipped_no_history': [], 'errors': []}
        self.settings.insert_one(dict(run))
        acquired = False
        try:
            acquired = self.acquire()
            if not acquired:
                run['status'] = 'skipped_overlap'
                return run
            if self.previous_owner is not None:
                self.settings.update_many(
                    {'kind': RUN_KIND, 'owner': self.previous_owner, 'status': 'running',
                     '_id': {'$ne': run_id}},
                    {'$set': {'status': 'interrupted', 'finished_at': utc_now(),
                              'errors': [{'error_type': 'InterruptedSweep'}]}},
                )
            channels, skipped, errors = self.inventory(heartbeat=self.renew)
            run.update(channels=len(channels), skipped_no_history=skipped, errors=errors)
            for channel, birthday in channels.items():
                self.renew()
                years = anniversary_age(birthday, today)
                if years is not None:
                    run['due'] += 1
                    self.queue(channel, years, today, channels)
            # Retry queued work even after its anniversary day has passed, but
            # never post to a channel removed from the active schedule.
            for event in self.settings.find({'kind': EVENT_KIND, 'complete': False}).batch_size(25):
                self.renew()
                if event['channel'] not in channels:
                    continue
                try:
                    if self.deliver(event):
                        run['completed'] += 1
                except Exception as exc:
                    run['errors'].append({'event': event['_id'], 'error_type': type(exc).__name__})
                    logger.warning('Anniversary event failed: %s (%s)', event['_id'], type(exc).__name__)
            for event in self.settings.find({'kind': EVENT_KIND, 'complete': False}).batch_size(25):
                run['pending'] += 1
                run['uncertain_messages'] += sum(part['state'] in ('sending', 'uncertain')
                                                 for part in event['deliveries'])
            run['status'] = 'partial' if run['pending'] or run['errors'] else 'success'
            return run
        except Exception as exc:
            run['status'] = 'failed'
            run['errors'].append({'error_type': type(exc).__name__})
            raise
        finally:
            run['finished_at'] = utc_now()
            try:
                self.settings.update_one({'_id': run['_id']}, {'$set': {
                    key: value for key, value in run.items() if key != '_id'
                }})
            finally:
                if acquired:
                    self.release()
            logger.info('Anniversary run %s: %s; due=%d complete=%d pending=%d uncertain=%d',
                        run['_id'], run['status'], run['due'], run['completed'],
                        run['pending'], run['uncertain_messages'])
