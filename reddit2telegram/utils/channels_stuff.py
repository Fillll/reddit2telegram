#encoding:utf-8

import os

import pymongo
import yaml


CHANNELS_COLLECTION = 'channels'


def get_config(config_filename=None):
    if config_filename is None:
        config_filename = os.path.join('configs', 'prod.yml')
    with open(config_filename) as config_file:
        return yaml.safe_load(config_file.read())


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
        'tags': kwargs['tags']
    }
    if 'min_upvotes_limit' in kwargs:
        details['min_upvotes_limit'] = kwargs['min_upvotes_limit']
    channels.insert_one(details)


if __name__ == '__main__':
    pass
