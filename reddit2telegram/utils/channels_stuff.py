#encoding:utf-8

import os
import importlib

import pymongo
import yaml


CHANNELS_COLLECTION = 'channels'


def get_config(config_filename=None):
    if config_filename is None:
        config_filename = os.path.join('configs', 'prod.yml')
    with open(config_filename) as config_file:
        return yaml.safe_load(config_file.read())


def import_submodule(submodule_name):
    if os.path.isdir(os.path.join('channels', submodule_name)):
        submodule = importlib.import_module(f'channels.{submodule_name}.app')
    else:
        submodule = DefaultChannel(submodule_name)
    return submodule


def set_new_channel(channel, **kwargs):
    channel = channel.replace('@', '')
    config = get_config()
    db = pymongo.MongoClient(host=config['db']['host'])[config['db']['name']]
    channels = db[CHANNELS_COLLECTION]
    is_any = channels.find_one({'submodule': channel.lower()})
    if is_any is not None:
        return
    details = {
        'submodule': channel.lower(),
        'channel': '@' + channel,
        'subreddit': kwargs['subreddit'],
        'tags': kwargs['tags'].lower(),
        'min_upvotes_limit': kwargs.get('min_upvotes_limit', None),
        'submissions_ranking': kwargs.get('submissions_ranking', 'hot'),
        'submissions_limit': kwargs.get('submissions_limit', 100)
    }
    channels.insert_one(details)


class DefaultChannel(object):
    '''docstring for DefaultChannel'''
    def __init__(self, submodule):
        super(DefaultChannel, self).__init__()
        self.submodule = submodule
        self.get_settings_from_db()
        if self.content is None:
            self.content = dict(
                text=True,
                gif=True,
                video=True,
                img=True,
                album=True,
                gallery=True,
                other=True
            )
        else:
            self.content['text'] = self.content.get('text', False)
            self.content['gif'] = self.content.get('gif', False)
            self.content['video'] = self.content.get('video', False)
            self.content['img'] = self.content.get('img', False)
            self.content['album'] = self.content.get('album', False)
            self.content['gallery'] = self.content.get('gallery', False)
            self.content['other'] = self.content.get('other', False)

    def get_settings_from_db(self):
        config = get_config()
        db = pymongo.MongoClient(host=config['db']['host'])[config['db']['name']]
        channels = db[CHANNELS_COLLECTION]
        channel_details = channels.find_one({'submodule': self.submodule})
        self.t_channel = channel_details.get('channel', None)
        self.submissions_ranking = channel_details.get('submissions_ranking', None)
        self.submissions_limit = channel_details.get('submissions_limit', None)
        self.subreddit = channel_details.get('subreddit', None)
        self.tags = channel_details.get('tags', None)
        self.min_upvotes_limit = channel_details.get('min_upvotes_limit', None)
        self.content = channel_details.get('content', None)

    def send_post(self, submission, r2t):
        return r2t.send_simple(submission,
            min_upvotes_limit=self.min_upvotes_limit,
            text=self.content['text'],
            gif=self.content['gif'],
            video=self.content['video'],
            img=self.content['img'],
            album=self.content['album'],
            gallery=self.content['gallery'],
            other=self.content['other']
        )
