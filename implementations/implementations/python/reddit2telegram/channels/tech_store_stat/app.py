#encoding:utf-8

from datetime import datetime
import random
import logging

import utils
from utils import SupplyResult
from utils.get_all_admins import get_admins_list
from utils.tech import get_dev_channel, get_all_public_submodules
from utils.tech import short_sleep
from utils.achievements import AchievementAnnouncements


subreddit = 'all'
t_channel = get_dev_channel()


GREAT_ACHIEVEMENTS = [
    3,
    10,
    42,
    50,
    69,
    100,
    123,
    200,
    300,
    333,
    420,
    500,
    600,
    666,
    700,
    800,
    900,
    1000,
    1234,
    2000,
    3000,
    3210,
    4000,
    4321,
    4444,
    5000,
    6000,
    7000,
    8000,
    9000,
    10000,
    12345,
    15000,
    20000,
    30000,
    40000,
    50000,
    54321,
    55555,
    60000,
    70000,
    80000,
    90000,
    100000,
    123456,
    200000,
    300000,
    400000,
    500000,
    600000,
    666666,
    700000,
    800000,
    900000,
    1000000
]


# This maintenance job must run even if Reddit is unavailable.
requires_submission = False


def _report(r2t, text, **kwargs):
    try:
        r2t.send_text(text, **kwargs)
    except Exception:
        logging.warning('Could not send achievement sweep status')


def send_post(submission, r2t):
    announcements = AchievementAnnouncements(r2t.settings, r2t.config)
    if not announcements.acquire():
        logging.info('Another achievement sweep is already running')
        return SupplyResult.STOP_THIS_SUPPLY
    try:
        return _sweep(r2t, announcements)
    finally:
        announcements.release()


def _sweep(r2t, announcements):
    _report(r2t, 'Regular bypass started.')
    total = dict(channels=0, members=0, admins=0, errors=0, prev_members=0)
    all_submodules = list(get_all_public_submodules())
    number_of_modules = len(all_submodules)
    sleep_coef = 2000 / 3 / 2 / max(number_of_modules, 1)
    channels_stat = {}
    seen_channels = set()

    for submodule_name in random.sample(all_submodules, k=number_of_modules):
        announcements.renew()
        short_sleep(sleep_coef)
        try:
            submodule = utils.channels_stuff.import_submodule(submodule_name)
            channel_name = submodule.t_channel
            # Technical destinations and duplicate schedules are not separate
            # public channels and must not generate milestone announcements.
            if not isinstance(channel_name, str) or not channel_name.startswith('@'):
                continue
            if channel_name.lower() in seen_channels:
                continue
            seen_channels.add(channel_name.lower())
        except Exception:
            total['errors'] += 1
            logging.warning('Could not load channel %s during achievement sweep', submodule_name)
            continue

        stat_to_store = {
            'channel': channel_name.lower(), 'ts': datetime.utcnow(),
            'submodule': submodule_name,
        }
        total['channels'] += 1
        try:
            admins = get_admins_list(r2t, channel_name)
            stat_to_store['admins'] = admins
            total['admins'] += len(admins)
        except Exception:
            total['errors'] += 1
            _report(r2t, 'Failed to get admins for {channel}.'.format(channel=channel_name))
            logging.warning('Failed to get admins for %s', channel_name)

        short_sleep(sleep_coef)
        try:
            current_members_cnt = r2t.get_chat_members_count(chat_id=channel_name)
            # An admin-only failure snapshot must not hide the last valid count.
            previous = r2t.stats.find_one(
                {'channel': channel_name.lower(), 'members_cnt': {'$gte': 0}},
                sort=[('ts', -1)],
            )
            # A first observation establishes a baseline, rather than announcing
            # every historical milestone for a newly added channel.
            prev_members_cnt = previous['members_cnt'] if previous else current_members_cnt
            for achievement in GREAT_ACHIEVEMENTS:
                if prev_members_cnt < achievement <= current_members_cnt:
                    announcements.queue(submodule_name, channel_name, achievement)
            # Persist the crossing before advancing the statistics checkpoint.
            stat_to_store['members_cnt'] = current_members_cnt
            r2t.stats.insert_one(stat_to_store)
            total['members'] += current_members_cnt
            total['prev_members'] += prev_members_cnt
            channels_stat[channel_name] = {
                'prev_cnt': prev_members_cnt, 'curr_cnt': current_members_cnt,
                'diff': current_members_cnt - prev_members_cnt,
                'perc_diff': ((current_members_cnt - prev_members_cnt) / prev_members_cnt
                              if prev_members_cnt else 0),
            }
        except Exception:
            total['errors'] += 1
            _report(r2t, 'Failed to collect statistics or queue milestones for {channel}.'.format(
                channel=channel_name))
            logging.warning('Failed to collect statistics or queue milestones for %s', channel_name)

    # Retry durable events regardless of whether the channel crossed a milestone
    # again, lost subscribers, or could not be inspected in this sweep.
    for event in announcements.pending():
        announcements.renew()
        try:
            announcements.deliver(event)
        except Exception as exc:
            total['errors'] += 1
            r2t.settings.update_one({'_id': event['_id']}, {'$set': {
                'last_error_type': type(exc).__name__, 'last_failure_at': datetime.utcnow(),
            }})
            logging.warning('Milestone delivery pending: %s (%s)', event['_id'], type(exc).__name__)
            _report(r2t, 'Milestone delivery pending: {channel}, {achievement} subscribers.'.format(
                **event))

    members_diff = total['members'] - total['prev_members']
    perc_diff = round((members_diff / total['prev_members']) * 100, 2) if total['prev_members'] else 0
    if members_diff < 0:
        sign = ''
    elif members_diff == 0:
        sign = '±'
    else:
        sign = '+'

    text_to_send = 'Ok, regular bypass results.\n\n'
    text_to_send += '<pre>Active channels: {n}.</pre>\n'.format(n=total['channels'])
    text_to_send += '<pre>Subscribers: {n}.</pre>\n'.format(n=total['members'])
    text_to_send += '<pre>Cnt diff: {sign}{diff} ({sign}{perc_diff}%).</pre>\n'.format(
        n=total['members'],
        sign=sign,
        diff=members_diff,
        perc_diff=perc_diff
    )
    text_to_send += '<pre>Admins: {n}.</pre>\n'.format(n=total['admins'])
    text_to_send += '<pre>Errors during bypass: {n}.</pre>\n'.format(n=total['errors'])
    text_to_send += '\n<i>See you!</i>'
    _report(r2t, text_to_send, parse_mode='HTML')
    short_sleep()
    text_to_send = '📈 <b>TOP 5 GAIN</b> 📈\n'
    top_5_gain = dict(sorted(channels_stat.items(), key=lambda item: item[1]['diff'], reverse=True)[:5])
    bottom_5_gain = dict(sorted(channels_stat.items(), key=lambda item: item[1]['diff'])[:5])
    for k, v in top_5_gain.items():
        if v['diff'] < 0:
            sign = ''
        elif v['diff'] == 0:
            sign = '±'
        else:
            sign = '+'
        text_to_send += '{channel}: {from_cnt} {s}{diff} ({s}{perc_diff}%) → {to_cnt}\n'.format(
            channel=k,
            from_cnt=v['prev_cnt'],
            s=sign,
            diff=v['diff'],
            to_cnt=v['curr_cnt'],
            perc_diff=round(v['perc_diff'] * 100, 2)
        )
    _report(r2t, text_to_send, parse_mode='HTML')
    short_sleep()
    text_to_send = '📉 <b>TOP 5 FALL</b> 📉\n'
    for k, v in bottom_5_gain.items():
        if v['diff'] < 0:
            sign = ''
        elif v['diff'] == 0:
            sign = '±'
        else:
            sign = '+'
        text_to_send += '{channel}: {from_cnt} {s}{diff} ({s}{perc_diff}%) → {to_cnt}\n'.format(
            channel=k,
            from_cnt=v['prev_cnt'],
            s=sign,
            diff=v['diff'],
            to_cnt=v['curr_cnt'],
            perc_diff=round(v['perc_diff'] * 100, 2)
        )
    _report(r2t, text_to_send, parse_mode='HTML')
    # It's not a proper supply, so just stop.
    return SupplyResult.STOP_THIS_SUPPLY
