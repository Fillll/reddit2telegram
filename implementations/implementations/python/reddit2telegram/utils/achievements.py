"""Durable milestone delivery, independent of the next subscriber snapshot."""

from datetime import datetime, timedelta
import logging
from uuid import uuid4

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

import utils
from utils import SupplyResult
from utils.promotion import make_nice_submission


ANNOUNCEMENTS_CHANNEL = '@reddit2telegram'
SETTING_NAME = 'r2t_achievements'
EVENT_SETTING = 'r2t_achievement_delivery'
LOCK_ID = 'r2t_achievement_sweep_lock'
LEASE = timedelta(hours=2)


class AchievementAnnouncements:
    def __init__(self, settings, config):
        self.settings = settings
        self.config = config
        self.owner = uuid4().hex

    def acquire(self):
        try:
            self.settings.update_one(
                {'_id': LOCK_ID},
                {'$setOnInsert': {'setting': LOCK_ID, 'expires_at': datetime.min}}, upsert=True
            )
        except DuplicateKeyError:
            # Another sweep created the same lock between match and upsert.
            pass
        now = datetime.utcnow()
        return self.settings.find_one_and_update(
            {'_id': LOCK_ID, 'expires_at': {'$lte': now}},
            {'$set': {'owner': self.owner, 'expires_at': now + LEASE}},
            return_document=ReturnDocument.AFTER,
        ) is not None

    def renew(self):
        now = datetime.utcnow()
        result = self.settings.update_one(
            {'_id': LOCK_ID, 'owner': self.owner, 'expires_at': {'$gt': now}},
            {'$set': {'expires_at': now + LEASE}},
        )
        if not result.matched_count:
            raise RuntimeError('Achievement sweep lease expired or changed owner')

    def release(self):
        self.settings.update_one(
            {'_id': LOCK_ID, 'owner': self.owner},
            {'$set': {'expires_at': datetime.min}},
        )

    def queue(self, submodule, channel, achievement):
        channel = channel.lower()
        legacy = self.settings.find_one({'setting': SETTING_NAME}) or {}
        if achievement in legacy.get('channels', {}).get(channel, []):
            return
        # The built-in unique _id index prevents concurrent duplicate events.
        event_id = f'{EVENT_SETTING}:{channel}:{achievement}'
        self.settings.update_one(
            {'_id': event_id},
            {'$setOnInsert': {
                'setting': event_id, 'kind': EVENT_SETTING, 'submodule': submodule,
                'channel': channel, 'achievement': achievement,
                'complete': False, 'message_ids': [], 'forwarded_ids': [],
                'created_at': datetime.utcnow(),
            }},
            upsert=True,
        )

    def pending(self):
        return self.settings.find({'kind': EVENT_SETTING, 'complete': False})

    def deliver(self, event):
        from supplier import send_to_channel_from_subreddit

        self.renew()
        selector = {'_id': event['_id']}
        self.settings.update_one(selector, {'$inc': {'attempts': 1},
                                            '$set': {'last_attempt_at': datetime.utcnow()}})
        message_ids = list(event['message_ids'])

        def remember(ids):
            # Save each acknowledged part before attempting the next one. If a
            # gallery partially fails, retain its announcement and forward the
            # parts actually published instead of posting it again.
            message_ids.extend(ids)
            self.settings.update_one(selector, {'$addToSet': {'message_ids': {'$each': ids}}})

        if not message_ids:
            posting_attempted = False

            def post(submission, sender, **kwargs):
                nonlocal posting_attempted
                posting_attempted = True
                sender.on_message_sent = remember
                try:
                    result = make_nice_submission(submission, sender, **kwargs)
                    if message_ids and result != SupplyResult.SUCCESSFULLY:
                        # A rejected gallery may already have sent its heading.
                        # Do not let the supplier publish another candidate.
                        return SupplyResult.STOP_THIS_SUPPLY
                    return result
                finally:
                    sender.on_message_sent = None

            try:
                submodule = utils.channels_stuff.import_submodule(event['submodule'])
                send_to_channel_from_subreddit(
                    how_to_post=post, channel_to_post=ANNOUNCEMENTS_CHANNEL,
                    subreddit=submodule.subreddit,
                    submodule_name_to_promte=event['submodule'],
                    channel_to_promote=event['channel'],
                    submissions_ranking='top', submissions_limit=1000,
                    config=self.config, extra_args=True,
                    announcement_heading=('🏆 Great achievement!\n{channel}\n'
                                          '💪 Milestone of {number} subscribers.\n\n').format(
                        channel=event['channel'], number=event['achievement']),
                )
            except Exception:
                if not message_ids and posting_attempted:
                    # A Telegram request may have been accepted even though its
                    # response was lost. Leave this event for the next sweep.
                    raise
                logging.warning('Milestone %s: Reddit or a later posting step failed', event['_id'])

            if not message_ids:
                # No usable Reddit candidate (or an unavailable Reddit source)
                # must not suppress a milestone whose channel/count are known.
                with utils.Reddit2TelegramSender(ANNOUNCEMENTS_CHANNEL, self.config) as sender:
                    sender.on_message_sent = remember
                    result = sender.send_text(
                        '🏆 Great achievement!\n{channel}\n💪 Milestone of {number} subscribers.'.format(
                            channel=event['channel'], number=event['achievement']))
                    if result != SupplyResult.SUCCESSFULLY or not message_ids:
                        raise RuntimeError('Milestone announcement was not acknowledged')

        self.renew()
        self.settings.update_one(selector, {'$addToSet': {'message_ids': {'$each': message_ids}}})
        # Keep the existing achievement history, using an atomic update so one
        # channel cannot overwrite another channel's completed milestones.
        self.settings.update_one(
            {'setting': SETTING_NAME},
            {'$addToSet': {f"channels.{event['channel']}": event['achievement']}},
            upsert=True,
        )
        if event['channel'] != ANNOUNCEMENTS_CHANNEL:
            with utils.Reddit2TelegramSender(event['channel'], self.config) as sender:
                for message_id in message_ids:
                    if message_id in event['forwarded_ids']:
                        continue
                    self.renew()
                    sender.forward_message(
                        chat_id=event['channel'], from_chat_id=ANNOUNCEMENTS_CHANNEL,
                        message_id=message_id,
                    )
                    self.settings.update_one(selector, {'$addToSet': {'forwarded_ids': message_id}})
        self.settings.update_one(selector, {'$set': {'complete': True, 'completed_at': datetime.utcnow()}})
