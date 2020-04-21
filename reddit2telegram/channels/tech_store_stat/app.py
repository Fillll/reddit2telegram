#encoding:utf-8

import importlib
import time
from datetime import datetime
import random
import logging

from utils import SupplyResult
from utils.get_all_admins import get_admins_list
from utils.tech import get_dev_channel, get_all_submodules, get_last_members_cnt


subreddit = 'all'
t_channel = get_dev_channel()


def send_post(submission, r2t):
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
            members = r2t.telepot_bot.getChatMembersCount(channel_name)
            stat_to_store['members_cnt'] = members
            total['members'] += members
            total['prev_members'] += get_last_members_cnt(r2t, channel_name)
        except Exception as e:
            total['errors'] += 1
            err_to_send = 'Failed to get members count for {channel}.'.format(channel=channel_name)
            r2t.send_text(err_to_send)
            logging.error(err_to_send)
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
