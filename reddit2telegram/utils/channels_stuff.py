#encoding:utf-8

import os
import importlib

import pymongo
import yaml

import default_channel


CHANNELS_COLLECTION = 'channels'


def get_config(config_filename=None):
    if config_filename is None:
        config_filename = os.path.join('configs', 'prod.yml')
    with open(config_filename) as config_file:
        return yaml.safe_load(config_file.read())


def import_submodule(submodule_name):
    if os.path.isdir(os.path.join('channels', submodule_name)):
        submodule = importlib.import_module('channels.{}.app'.format(submodule_name))
    else:
        submodule = default_channel.DefaultChannel(submodule_name)
    return submodule


def set_new_channel(channel, **kwargs):
    config = get_config()
    db = pymongo.MongoClient(host=config['db']['host'])[config['db']['name']]
    channels = db[CHANNELS_COLLECTION]
    is_any = channels.find_one({'submodule': channel.lower()})
    if is_any is not None:
        return
    details = {
        'submodule':channel.lower(),
        'channel': '@' + channel,
        'subreddit': kwargs['subreddit'],
        'tags': kwargs['tags'],
        'min_upvotes_limit': kwargs.get('min_upvotes_limit', None),
        'submissions_ranking': kwargs.get('submissions_ranking', 'hot'),
        'submissions_limit': kwargs.get('submissions_limit', 100)
    }
    channels.insert_one(details)
