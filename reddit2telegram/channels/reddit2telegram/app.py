#encoding:utf-8

import importlib
import random
from datetime import datetime
import os
import hashlib

import pymongo

from utils import SupplyResult
from utils.tech import get_all_public_submodules
from utils.setup import get_config


SETTING_NAME = 'r2t_promotion_queue'


def update_promotion_order():
    config = get_config()
    db = pymongo.MongoClient(host=config['db']['host'])[config['db']['name']]
    settings = db['settings']
    first_date_view = db['view_with_first_dates']
    all_submodules = get_all_public_submodules()
    all_submodules.remove('reddit2telegram')
    submodules_and_dates = dict()
    for submodule in all_submodules:
        imported = importlib.import_module('channels.{}.app'.format(submodule))
        channel = imported.t_channel
        first_date_result = first_date_view.find_one({'_id': channel.lower()})
        if first_date_result is None:
            continue
        submodules_and_dates[submodule] = first_date_result['first_date']
    if settings.find_one({'setting': SETTING_NAME}) is None:
        settings.insert_one({
            'setting': SETTING_NAME,
            'promotion_order': submodules_and_dates,
            'already_promoted': list(),
            'counter': 0
        })
    settings.find_one_and_update(
        {
            'setting': SETTING_NAME
        },
        {
            '$set': 
            {
                'promotion_order': submodules_and_dates
            }
        }
    )


def what_submodule():
    now = datetime.now()
    if now.weekday() == 6:  # if Sunday then random
        all_submodules = get_all_public_submodules()
        all_submodules.remove('reddit2telegram')
        return random.choice(all_submodules)

    config = get_config()
    db = pymongo.MongoClient(host=config['db']['host'])[config['db']['name']]
    settings = db['settings']
    if settings.find_one({'setting': SETTING_NAME}) is None:
        update_promotion_order()
    setting_result = settings.find_one({'setting': SETTING_NAME})

    already_promoted = setting_result['already_promoted']
    promotion_order = setting_result['promotion_order']

    for submodule in sorted(promotion_order.keys(), key=promotion_order.get, reverse=1):
        if submodule not in already_promoted:
            return submodule

    # If every is promoted.
    settings.find_one_and_update(
        {
            'setting': SETTING_NAME
        },
        {
            '$inc': {
                'counter': 1
            },
            '$set': {
                'already_promoted': list()
            }
        }
    )


def what_subreddit(submodule_name_to_promte):
    submodule_to_promote = importlib.import_module('channels.{}.app'.format(submodule_name_to_promte))
    return submodule_to_promote.subreddit


def what_channel(submodule_name_to_promte):
    submodule_to_promote = importlib.import_module('channels.{}.app'.format(submodule_name_to_promte))
    return submodule_to_promote.t_channel


def get_tags(submodule_name_to_promte):
    tags_filename = os.path.join('channels', submodule_name_to_promte, 'tags.txt')
    if not os.path.exists(tags_filename):
        return None
    with open(tags_filename, 'r') as tags_file:
        tags = tags_file.read()
        return tags.split()


def make_nice_submission(submission, r2t, submodule_name_to_promte, extra_ending=None, **kwargs):
    tags = get_tags(submodule_name_to_promte)
    tags_string = ''
    if tags is not None:
        if len(tags) > 0:
            tags_string = ' '.join(tags)
    if extra_ending is None:
        extra_ending = ''
    submission.title  # to make it non-lazy
    result = r2t.send_simple(submission,
        channel_to_promote=what_channel(submodule_name_to_promte),
        date=datetime.utcfromtimestamp(submission.created_utc).strftime('%Y %b %d'),
        tags=tags_string,
        extra_ending=extra_ending,
        text='{title}\n\n{self_text}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{date}\n{short_link}\nby {channel_to_promote}\n{tags}\n\n{extra_ending}',
        other='{title}\n{link}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{date}\n{short_link}\nby {channel_to_promote}\n{tags}\n\n{extra_ending}',
        album='{title}\n{link}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{date}\n{short_link}\nby {channel_to_promote}\n{tags}\n\n{extra_ending}',
        gif='{title}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{date}\n{short_link}\nby {channel_to_promote}\n{tags}\n\n{extra_ending}',
        img='{title}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{date}\n{short_link}\nby {channel_to_promote}\n{tags}\n\n{extra_ending}',
        video='{title}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{date}\n{short_link}\nby {channel_to_promote}\n{tags}\n\n{extra_ending}'
    )
    return result


submodule_name_to_promte = what_submodule()


subreddit = what_subreddit(submodule_name_to_promte)
t_channel = '@reddit2telegram'
submissions_ranking = 'top'
submissions_limit = 1000


def send_post(submission, r2t):
    now = datetime.now()
    today = datetime(now.year, now.month, now.day)
    taday_date_string = today.strftime('%Y %b %d')
    random_number = abs(int(hashlib.sha1(taday_date_string.encode('utf-8')).hexdigest(), 16))
    # Twice a week update promotion order
    if (now.weekday() == 5) and (now.hour in [0, 23]) and (now.minute == 1):
        update_promotion_order()
        return SupplyResult.STOP_THIS_SUPPLY
    # If Saturday then no promotion
    if now.weekday() == 5:
        return SupplyResult.STOP_THIS_SUPPLY
    # If weekday or Sunday then regular promotion once a day
    if (now.weekday() != 5) and ((now.hour == random_number % 24) and (now.minute == random_number % 30)):
        result = make_nice_submission(submission, r2t, submodule_name_to_promte)
        if result == SupplyResult.SUCCESSFULLY:
            if now.weekday() < 5:
                config = get_config()
                db = pymongo.MongoClient(host=config['db']['host'])[config['db']['name']]
                settings = db['settings']
                settings.find_one_and_update(
                    {
                        'setting': SETTING_NAME
                    },
                    {
                        '$push':
                        {
                            'already_promoted': submodule_name_to_promte
                        }
                    }
                )
            return SupplyResult.SUCCESSFULLY
        return result
    return SupplyResult.STOP_THIS_SUPPLY
