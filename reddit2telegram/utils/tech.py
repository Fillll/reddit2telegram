#encoding:utf-8

import importlib
import csv
import yaml
import datetime
import random
import os
import time

import pymongo

import default_channel
import utils.channels_stuff


def get_dev_channel(config_filename=None):
    if config_filename is None:
        config_filename = os.path.join('configs', 'prod.yml')
    with open(config_filename) as config_file:
        config = yaml.safe_load(config_file.read())
        return config['telegram']['dev_chat']


def get_all_submodules(config_filename=None):
    if config_filename is None:
        config_filename = os.path.join('configs', 'prod.yml')
    with open(config_filename) as config_file:
        config = yaml.safe_load(config_file.read())
        all_submodules = set()
        with open(config['cron_file']) as tsv_file:
            tsv_reader = csv.DictReader(tsv_file, delimiter='\t')
            for row in tsv_reader:
                submodule_name = row['submodule_name']
                all_submodules.add(submodule_name)
        return all_submodules


def get_all_public_submodules(config_filename=None):
    all_submodules = get_all_submodules(config_filename=config_filename)
    return [submodule for submodule in all_submodules if 'tech_' not in submodule]


def get_all_public_channels(r2t, config_filename=None):
    all_submodules = get_all_submodules(config_filename)
    channels_and_dates = dict()
    for submodule_name in all_submodules:
        submodule = utils.channels_stuff.import_submodule(submodule_name)
        channel_name = submodule.t_channel
        if ('@' in channel_name) and (channel_name not in ['@r_channels_test', '@r_channels']):
            first_record_cursor = r2t.urls.find({
                'channel' : channel_name.lower()
            }).sort([('ts', pymongo.ASCENDING)]).limit(1)
            first_record_ts = first_record_cursor.next()['ts']
            channels_and_dates[channel_name] = first_record_ts
    return sorted(channels_and_dates.keys(), key=channels_and_dates.get)


def generate_list_of_channels(channels_list, random_permutation=False):
    if random_permutation:
        channels_list = random.sample(channels_list, k=len(channels_list))
    list_of_channels = ['{n}. {channel}'.format(n=str(i + 1).zfill(2), channel=channel)
                        for i, channel in enumerate(channels_list)]
    return list_of_channels


def get_active_period(r2t, channel_name):
    min_cursor = r2t.stats.find({'channel': channel_name.lower()}).sort([('ts', pymongo.ASCENDING)]).limit(1)
    min_ts = min_cursor.next()['ts']
    max_cursor = r2t.stats.find({'channel': channel_name.lower()}).sort([('ts', pymongo.DESCENDING)]).limit(1)
    max_ts = max_cursor.next()['ts']
    diff = max_ts - min_ts
    return diff.days


def get_last_members_cnt(r2t, channel_name):
    count_cursor = r2t.stats.find({'channel': channel_name.lower()}).sort([('ts', pymongo.DESCENDING)]).limit(1)
    last_cnt = count_cursor.next()['members_cnt']
    return last_cnt


def get_newly_active(r2t, channels_list):
    newly_active = list()
    for channel in channels_list:
        days_active = get_active_period(r2t, channel)
        if days_active <= 31:
            newly_active.append(channel)
    return newly_active


def get_top_growers_for_last_week(r2t, channels_list):
    last_week_diff = get_top_diff_for_last_week(r2t, channels_list)
    only_major_grow = {k: v['diff'] for k, v in last_week_diff.items() if v['diff'] >= 10}
    return sorted(only_major_grow, key=only_major_grow.get, reverse=True)[:3]


def no_chance_to_post_due_to_errors_cnt(r2t, channel_name):
    channel_name = channel_name.lower()
    how_many = number_of_errors_over_month(r2t, channel_name)
    r2t.t_channel = get_dev_channel()
    
    text_to_send = 'Total errors over last month is <b>' + str(how_many) + '</b>.\n'
    if how_many <= 12:
        # Send!
        probability_to_fail = 0.0
    elif how_many <= 99:
        probability_to_fail = how_many / 100
    else:
        probability_to_fail = 0.99
    if random.random() < probability_to_fail:
        # Not send.
        text_to_send += 'Probalitty to fail is <b>' + str(round(probability_to_fail, 2)) + '</b>.\n'
        text_to_send += 'And it failed.\n'
        text_to_send += channel_name
        r2t.send_text(text_to_send, parse_mode='HTML')
        return True
    else:
        # Send!
        return False


def number_of_errors_over_month(r2t, channel):
    channel = channel.lower()
    one_month_ago = datetime.datetime.utcnow() - datetime.timedelta(days=30)
    month_ago_cursor = r2t.errors.find({
        'channel': channel,
        'ts': {'$gte': one_month_ago}
    })
    errors_cnt = 0
    for error_record in month_ago_cursor:
        errors_cnt += error_record['cnt']
    return errors_cnt


def get_top_diff_for_last_week(r2t, channels_list):
    top_growers = dict()
    one_week_ago = datetime.datetime.utcnow() - datetime.timedelta(days=7)
    for channel in channels_list:
        week_ago_cursor = r2t.stats.find({
            'channel': channel.lower(),
            'ts': {'$gte': one_week_ago}
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
        top_growers[channel] = {
            'diff': grow,
            'last_week': week_ago_members_cnt,
            'now': current_members_cnt
        }
    return top_growers


def is_birthday_today(r2t, channel_name):
    today = datetime.datetime.utcnow().date()
    first_record_cursor = r2t.stats.find({
        'channel': channel_name.lower()
    }).sort([('ts', pymongo.ASCENDING)]).limit(5)
    birth_date = None
    for record in first_record_cursor:
        if 'ts' in record:
            birth_date = record['ts']
            break
    if birth_date is None:
        return False, None
    year_diff = today.year - birth_date.year
    if birth_date.replace(year=today.year).date() == today:
        return True, year_diff
    else:
        return False, None


def default_ending():
    text_to_send = '🙋\nQ: How can I help?\nA: Support us on Patreon and promote your favorite channels!\n\n'
    text_to_send += 'Q: How to make similar channels?\nA: Ask at @r_channels or use manual at https://github.com/Fillll/reddit2telegram.\n\n'
    text_to_send += 'Q: Where to donate?\nA: Patreon: https://www.patreon.com/reddit2telegram. Other ways: https://bit.ly/r2t_donate.'
    return text_to_send


def get_all_tags(config_filename=None):
    all_submodules = get_all_public_submodules(config_filename=config_filename)
    all_tags = set()
    for submodule in all_submodules:
        if os.path.isdir(os.path.join('channels', submodule_name)):
            tags_filename = os.path.join('channels', submodule, 'tags.txt')
            if not os.path.exists(tags_filename):
                continue
            with open(tags_filename, 'r') as tags_file:
                tags = tags_file.read()
                all_tags.update(tags.split())
        else:
            submodule = default_channel.DefaultChannel(submodule_name)
            all_tags.update(submodule.tags.split())
    return all_tags


def chunker(seq, size):
    # https://stackoverflow.com/questions/434287/what-is-the-most-pythonic-way-to-iterate-over-a-list-in-chunks
    return (seq[pos:pos + size] for pos in range(0, len(seq), size))


def short_sleep(coef=1):
    time.sleep(random.uniform(2 * coef, 4 * coef))


def long_sleep(coef=1):
    time.sleep(random.uniform(8 * coef, 20 * coef))
