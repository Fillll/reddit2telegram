#encoding:utf-8

import csv
import importlib
import random
import datetime

import pymongo
import yaml

from utils import SupplyResult


subreddit = 'all'
t_channel = '@r_channels'


def get_active_period(r2t, channel_name):
    min_cursor = r2t.stats.find({'channel' : channel_name.lower()}).sort([('ts', pymongo.ASCENDING)]).limit(1)
    min_ts = min_cursor.next()['ts']
    max_cursor = r2t.stats.find({'channel' : channel_name.lower()}).sort([('ts', pymongo.DESCENDING)]).limit(1)
    max_ts = max_cursor.next()['ts']
    diff = max_ts - min_ts
    return diff.days


def get_newly_active(r2t, channels_list):
    newly_active = list()
    for channel in channels_list:
        days_active = get_active_period(r2t, channel)
        if days_active <= 31:
            newly_active.append(channel)
    return newly_active


def get_top_growers_for_last_week(r2t, channels_list):
    top_growers = dict()
    now = datetime.datetime.now()
    for channel in channels_list:
        week_ago_cursor = r2t.stats.find({
            'channel': channel.lower(),
            'ts': {'$gte': now - datetime.timedelta(days=7)}
        }).sort([('ts', pymongo.ASCENDING)]).limit(100)
        for stat_record in week_ago_cursor:
            if 'members_cnt' in stat_record:
                week_ago_members_cnt = stat_record['members_cnt']
                break
        current_cursor = r2t.stats.find({'channel': channel.lower()}).sort([('ts', pymongo.DESCENDING)]).limit(100)
        for stat_record in current_cursor:
            if 'members_cnt' in stat_record:
                current_members_cnt = stat_record['members_cnt']
                break
        grow = current_members_cnt - week_ago_members_cnt
        if grow >= 10:
            top_growers[channel] = grow
    return sorted(top_growers, key=top_growers.get, reverse=True)[:3]


def send_post(submission, r2t):
    config_filename = 'configs/prod.yml'
    with open(config_filename) as config_file:
        config = yaml.load(config_file.read())
    channels_list = list()
    with open(config['cron_file']) as tsv_file:
        tsv_reader = csv.DictReader(tsv_file, delimiter='\t')
        for row in tsv_reader:
            submodule_name = row['submodule_name']
            submodule = importlib.import_module('channels.{}.app'.format(submodule_name))
            channel_name = submodule.t_channel
            
            if ('@' in channel_name) and (channel_name not in ['@r_channels_test', '@r_channels']):
                channels_list.append(channel_name)
    newly_active = get_newly_active(r2t, channels_list)
    text_to_send = '<b>Weekend news</b>\n\n'
    if len(newly_active) > 0:
        text_to_send += '🎉 Welcome to newly active channels: {channels_list}. 🎈🎈\n\n'.format(channels_list=', '.join(newly_active))
    text_to_send += '🏆 Channel of the week: {channel_name}. Join and enjoy!\n\n'.format(channel_name=random.choice(channels_list))
    top_growers = get_top_growers_for_last_week(r2t, channels_list)
    if len(top_growers) > 0:
        text_to_send += '🔥 Hottest channels of the week: {channels}.\n\n'.format(channels=', '.join(top_growers))
    list_of_channels = ['{n}. {channel}'.format(n=str(i + 1).zfill(2), channel=channel)
                            for i, channel in enumerate(random.sample(channels_list, k=len(channels_list)))]
    text_to_send += '⬇️ All active channels:\n{list_of_channels}\n\n'.format(list_of_channels='\n'.join(list_of_channels))
    text_to_send += '🙋\nQ: How can I help?\nA: Promote your favorite channels!\n\n'
    text_to_send += 'Q: How to make similar channels?\nA: Ask here or use manual at https://github.com/Fillll/reddit2telegram.\n\n'
    text_to_send += 'Q: Where to donate?\nA: http://bit.ly/r2t_donate'
    r2t.send_text(text_to_send, parse_mode='HTML')
    # It's not a proper supply, so just stop.
    return SupplyResult.STOP_THIS_SUPPLY
