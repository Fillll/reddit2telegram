#encoding:utf-8

import csv
import importlib
import time
from datetime import datetime

import yaml

from utils import SupplyResult
from utils.get_all_admins import get_admins_list


def get_dev_channel(config_filename=None):
    config_filename = 'configs/prod.yml'
    with open(config_filename) as config_file:
        config = yaml.load(config_file.read())
        return config['telegram']['dev_chat']


subreddit = 'all'
t_channel = get_dev_channel()


def send_post(submission, r2t):
    r2t.send_text('Regular bypass started.')
    time.sleep(1)
    config_filename = 'configs/prod.yml'
    with open(config_filename) as config_file:
        config = yaml.load(config_file.read())
    total = {
        'channels': 0,
        'members': 0,
        'admins': 0,
        'errors': 0
    }
    all_channels = set()
    with open(config['cron_file']) as tsv_file:
        tsv_reader = csv.DictReader(tsv_file, delimiter='\t')
        for row in tsv_reader:
            submodule_name = row['submodule_name']
            all_channels.add(submodule_name)
    for submodule_name in all_channels:
        time.sleep(10)
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
            logging.error('Failed to get admins for {channel}.'.format(channel=channel_name))
        time.sleep(2)
        try:
            members = r2t.telepot_bot.getChatMembersCount(channel_name)
            stat_to_store['members_cnt'] = members
            total['members'] += members
        except Exception as e:
            total['errors'] += 1
            logging.error('Failed to get members count for {channel}.'.format(channel=channel_name))
        r2t.stats.insert_one(stat_to_store)
    text_to_send = 'Ok, regular bypass results.\n\n'
    text_to_send += '<pre>Active channels: {n}.</pre>\n'.format(n=total['channels'])
    text_to_send += '<pre>Subscribers: {n}.</pre>\n'.format(n=total['members'])
    text_to_send += '<pre>Admins: {n}.</pre>\n'.format(n=total['admins'])
    text_to_send += '<pre>Errors during bypass: {n}.</pre>\n'.format(n=total['errors'])
    text_to_send += '\n<i>See you!</i>'
    r2t.send_text(text_to_send, parse_mode='HTML')
    # It's not a proper supply, so just stop.
    return SupplyResult.STOP_THIS_SUPPLY
