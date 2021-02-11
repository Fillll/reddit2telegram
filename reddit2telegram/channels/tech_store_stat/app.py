#encoding:utf-8

import importlib
from datetime import datetime
import random
import logging

import pymongo

import utils
from utils import SupplyResult
from utils.get_all_admins import get_admins_list
from utils.tech import get_dev_channel, get_all_submodules, get_last_members_cnt
from utils.setup import get_config
from utils.tech import short_sleep, long_sleep
from supplier import send_to_channel_from_subreddit
from channels.reddit2telegram.app import make_nice_submission


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
    4000,
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
    700000,
    800000,
    900000,
    1000000
]


SETTING_NAME = 'r2t_achievements'


SLEEP_COEF = (2.718281828 / 3.14159) ** 2.718281828


def say_congrats(submodule_name, channel, achievement):
    short_sleep()
    config = get_config()
    submodule = importlib.import_module('channels.{}.app'.format(submodule_name))
    subreddit_name = submodule.subreddit
    send_to_channel_from_subreddit(
        how_to_post=make_nice_submission,
        channel_to_post='@reddit2telegram',
        subreddit=subreddit_name,
        submodule_name_to_promte=submodule_name,
        submissions_ranking='top',
        submissions_limit=1000,
        config=config,
        extra_args=True,
        extra_ending='🏆 Great achievement!\n💪 Milestone of {number} subscribers.'.format(
            number=achievement
        )
    )
    long_sleep()


def set_achievement(submodule_name, channel, achievement, settings):
    if settings.find_one({'setting': SETTING_NAME}) is None:
        settings.insert_one({
            'setting': SETTING_NAME,
            'channels': {
                channel.lower(): [achievement]
            }
        })
    else:
        current_state = settings.find_one({'setting': SETTING_NAME})
        channels = current_state['channels']
        if channel.lower() in channels:
            channels[channel.lower()].append(achievement)
        else:
            channels[channel.lower()] = [achievement]
        settings.find_one_and_update(
            {
                'setting': SETTING_NAME
            },
            {
                '$set': 
                {
                    'channels': channels
                }
            }
        )
    say_congrats(submodule_name, channel, achievement)


def send_post(submission, r2t):
    # To check previous achievements
    config = get_config()
    db = pymongo.MongoClient(host=config['db']['host'])[config['db']['name']]
    settings = db['settings']
    # Start logging!
    r2t.send_text('Regular bypass started.')
    short_sleep()
    total = {
        'channels': 0,
        'members': 0,
        'admins': 0,
        'errors': 0,
        'prev_members': 0
    }
    all_submodules = get_all_submodules()
    channels_stat = dict()
    for submodule_name in random.sample(all_submodules, k=len(all_submodules)):
        short_sleep(SLEEP_COEF)
        submodule = importlib.import_module('channels.{}.app'.format(submodule_name))
        channel_name = submodule.t_channel
        stat_to_store = {
            'channel': channel_name.lower(),
            'ts': datetime.utcnow(),
            'submodule': submodule_name
        }
        total['channels'] += 1
        try:
            admins = get_admins_list(r2t, channel_name)
            stat_to_store['admins'] = admins
            total['admins'] += len(admins)
        except Exception as e:
            total['errors'] += 1
            err_to_send = 'Failed to get admins for {channel}.'.format(channel=channel_name)
            r2t.send_text(err_to_send)
            logging.error(err_to_send)
        short_sleep(SLEEP_COEF)
        try:
            current_members_cnt = r2t.telegram_bot.get_chat_members_count(chat_id=channel_name)
            stat_to_store['members_cnt'] = current_members_cnt
            total['members'] += current_members_cnt
            prev_members_cnt = get_last_members_cnt(r2t, channel_name)
            total['prev_members'] += prev_members_cnt
            channels_stat[channel_name] = {
                'prev_cnt': prev_members_cnt,
                'curr_cnt': current_members_cnt,
                'diff': current_members_cnt - prev_members_cnt,
                'perc_diff': (current_members_cnt - prev_members_cnt) / prev_members_cnt
            }
        except Exception as e:
            total['errors'] += 1
            err_to_send = 'Failed to get members count for {channel}.'.format(channel=channel_name)
            r2t.send_text(err_to_send)
            logging.error(err_to_send)
        else:
            # If they pass something special
            for achievement in GREAT_ACHIEVEMENTS:
                if (prev_members_cnt < achievement) and (achievement <= current_members_cnt):
                    # Achievement reached
                    r2t.send_text('🏆 {channel}\n{n1} ➡️ {n2}'.format(
                        n1=prev_members_cnt,
                        n2=current_members_cnt,
                        channel=channel_name
                    ))
                    setting_result = settings.find_one({'setting': SETTING_NAME})
                    if setting_result is None:
                        set_achievement(submodule_name, channel_name, achievement, settings)
                    elif channel_name.lower() not in setting_result['channels']:
                        set_achievement(submodule_name, channel_name, achievement, settings)
                    elif achievement not in setting_result['channels'][channel_name.lower()]:
                        set_achievement(submodule_name, channel_name, achievement, settings)
                    else:
                        # Was already archived
                        long_sleep()
        
        r2t.stats.insert_one(stat_to_store)

    members_diff = total['members'] - total['prev_members']
    perc_diff = round((members_diff / total['prev_members']) * 100, 2)
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
    r2t.send_text(text_to_send, parse_mode='HTML')
    short_sleep()
    text_to_send = '📈 TOP 5 GAIN 📈\n'
    top_5_gain = dict(sorted(channels_stat.items(), key=lambda item: item[1]['diff'], reverse=True)[:5])
    bottom_5_gain = dict(sorted(channels_stat.items(), key=lambda item: item[1]['diff'])[:5])
    for k, v in top_5_gain.items():
        if v['diff'] < 0:
            sign = ''
        elif v['diff'] == 0:
            sign = '±'
        else:
            sign = '+'
        text_to_send += '{channel}: {from_cnt} → {s}{diff} ({s}{perc_diff}%) → {to_cnt}\n'.format(
            channel=k,
            from_cnt=v['prev_cnt'],
            s=sign,
            diff=v['diff'],
            to_cnt=v['curr_cnt'],
            perc_diff=round(v['perc_diff'] * 100, 3)
        )
    r2t.send_text(text_to_send)
    short_sleep()
    text_to_send = '📉 TOP 5 FALL 📉\n'
    for k, v in bottom_5_gain.items():
        if v['diff'] < 0:
            sign = ''
        elif v['diff'] == 0:
            sign = '±'
        else:
            sign = '+'
        text_to_send += '{channel}: {from_cnt} → {s}{diff} ({s}{perc_diff}%) → {to_cnt}\n'.format(
            channel=k,
            from_cnt=v['prev_cnt'],
            s=sign,
            diff=v['diff'],
            to_cnt=v['curr_cnt'],
            perc_diff=round(v['perc_diff'] * 100, 3)
        )
    r2t.send_text(text_to_send)
    # It's not a proper supply, so just stop.
    return SupplyResult.STOP_THIS_SUPPLY
