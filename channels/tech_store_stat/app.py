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
    config_filename = 'configs/prod.yml'
    with open(config_filename) as config_file:
        config = yaml.load(config_file.read())
    with open(config['cron_file']) as tsv_file:
        tsv_reader = csv.DictReader(tsv_file, delimiter='\t')
        for row in tsv_reader:
            time.sleep(10)
            submodule_name = row['submodule_name']
            submodule = importlib.import_module('channels.{}.app'.format(submodule_name))
            channel_name = submodule.t_channel
            stat_to_store = {
                'channel': channel_name.lower(),
                'ts': datetime.utcnow(),
                'submodule': submodule_name
            }
            try:
                stat_to_store['admins'] = get_admins_list(r2t, channel_name)
            except Exception as e:
                logging.error('Failed to get admins for {channel}.'.format(channel=channel_name))
            time.sleep(2)
            try:
                stat_to_store['members_cnt'] = r2t.telepot_bot.getChatMembersCount(channel_name)
            except Exception as e:
                logging.error('Failed to get members count for {channel}.'.format(channel=channel_name))
            r2t.stats.insert_one(stat_to_store)
    # It's not a proper supply, so just stop.
    return SupplyResult.STOP_THIS_SUPPLY