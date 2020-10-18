#encoding:utf-8

import importlib
import time
from datetime import datetime
import random
import logging

import pymongo

from utils import SupplyResult
from utils.get_all_admins import get_admins_list
from utils.tech import get_dev_channel, get_all_submodules, get_last_members_cnt
from utils.setup import get_config


subreddit = 'all'
t_channel = get_dev_channel()


GREAT_ARCHIVEMENTS = [
    3,
    10,
    42,
    69,
    100,
    666,
    1000,
    2000,
    3000,
    4000,
    5000,
    10000,
    15000,
    50000,
    100000,
    500000,
    1000000
]


SETTING_NAME = 'r2t_archivements'


def send_post(submission, r2t):
    def say_congrats(channel, archivement):
        time.sleep(2)
        r2t.send_text('Great archivement for {channel}: {number} subscribers passed.'.format(
            channel=channel,
            number=archivement
        ))
        time.sleep(1)
    def set_archivement(channel, archivement):
        if settings.find_one({'setting': SETTING_NAME}) is None:
            settings.insert_one({
                'setting': SETTING_NAME,
                'channels': {
                    channel: [archivement]
                }
            })
        else:
            current_state = settings.find_one({'setting': SETTING_NAME})
            channels = current_state['channels']
            if channel in channels:
                channels[channel].append(archivement)
            else:
                channels[channel] = [archivement]
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
        say_congrats(channel, archivement)
    # To check previous archivements
    config = get_config()
    db = pymongo.MongoClient(host=config['db']['host'])[config['db']['name']]
    settings = db['settings']
    # Start logging!
    r2t.send_text('Regular bypass started.')
    time.sleep(1)
    total = {
        'channels': 0,
        'members': 0,
        'admins': 0,
        'errors': 0,
        'prev_members': 0
    }
    all_submodules = get_all_submodules()
    for submodule_name in random.sample(all_submodules, k=len(all_submodules)):
        time.sleep(2)
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
        time.sleep(2)
        try:
            current_members_cnt = r2t.telepot_bot.getChatMembersCount(channel_name)
            stat_to_store['members_cnt'] = current_members_cnt
            total['members'] += current_members_cnt
            prev_members_cnt = get_last_members_cnt(r2t, channel_name)
            total['prev_members'] += prev_members_cnt
        except Exception as e:
            total['errors'] += 1
            err_to_send = 'Failed to get members count for {channel}.'.format(channel=channel_name)
            r2t.send_text(err_to_send)
            logging.error(err_to_send)
        # If they pass something special
        for archivement in GREAT_ARCHIVEMENTS:
            if (prev_members_cnt < archivement) and (archivement <= current_members_cnt):
                # Archivement reached
                r2t.send_text('---\n{channel}\nWas: {n1} \t\t Now: {n2}'.format(
                    n1=prev_members_cnt,
                    n2=current_members_cnt,
                    channel=channel_name
                ))
                setting_result = settings.find_one({'setting': SETTING_NAME})
                if setting_result is None:
                    set_archivement(channel_name.lower(), archivement)
                elif channel_name.lower() not in setting_result['channels']:
                    set_archivement(channel_name.lower(), archivement)
                elif archivement not in setting_result['channels'][channel_name.lower()]:
                    set_archivement(channel_name.lower(), archivement)
                else:
                    # Was already archived
                    pass
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
    # It's not a proper supply, so just stop.
    return SupplyResult.STOP_THIS_SUPPLY
