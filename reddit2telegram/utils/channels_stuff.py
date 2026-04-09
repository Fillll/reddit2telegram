#encoding:utf-8

import os
import importlib
import re

import pymongo
import yaml


CHANNELS_COLLECTION = 'channels'
_SIMPLE_SEND_RE = re.compile(r'^\s*return\s+r2t\.send_simple\(submission\)\s*$')
_SUBREDDIT_URL_RE = re.compile(r'(?:https?://)?(?:www\.)?reddit\.com/r/([^/?#\s]+)', re.IGNORECASE)
_CHANNEL_URL_RE = re.compile(r'(?:https?://)?(?:t(?:elegram)?\.me/)([^/?#\s]+)', re.IGNORECASE)


def get_config(config_filename=None):
    if config_filename is None:
        config_filename = os.path.join('configs', 'prod.yml')
    with open(config_filename) as config_file:
        return yaml.safe_load(config_file.read())


def get_db(config_filename=None):
    config = get_config(config_filename=config_filename)
    return pymongo.MongoClient(host=config['db']['host'])[config['db']['name']]


def _get_channels_collection(config_filename=None):
    db = get_db(config_filename=config_filename)
    return db[CHANNELS_COLLECTION]


def get_channel_doc(submodule_name, config_filename=None):
    channels = _get_channels_collection(config_filename=config_filename)
    return channels.find_one({'submodule': submodule_name.lower()})


def is_simple_channel_module(submodule_name):
    app_path = os.path.join('channels', submodule_name, 'app.py')
    if not os.path.isfile(app_path):
        return False
    with open(app_path, 'r') as app_file:
        code = app_file.read()
    lines = [
        line.strip()
        for line in code.splitlines()
        if line.strip() and not line.strip().startswith('#')
    ]
    has_simple_send = any(_SIMPLE_SEND_RE.match(line) for line in lines)
    if not has_simple_send:
        return False
    for line in lines:
        if 'r2t.send_simple' in line and not _SIMPLE_SEND_RE.match(line):
            return False
    if sum(1 for line in lines if line.startswith('def ')) > 1:
        return False
    return True


def import_submodule(submodule_name):
    submodule_name = submodule_name.lower()
    channel_dir = os.path.join('channels', submodule_name)
    has_module = os.path.isdir(channel_dir)
    has_db = get_channel_doc(submodule_name) is not None

    if has_db and (not has_module or is_simple_channel_module(submodule_name)):
        return DefaultChannel(submodule_name)
    if has_module:
        return importlib.import_module(f'channels.{submodule_name}.app')
    return DefaultChannel(submodule_name)


def normalize_subreddit_name(subreddit):
    subreddit = subreddit.strip()
    subreddit = re.sub(r'^\s*subreddit\s*:\s*', '', subreddit, flags=re.IGNORECASE)
    match = _SUBREDDIT_URL_RE.search(subreddit)
    if match:
        subreddit = match.group(1)
    else:
        subreddit = subreddit.strip().strip('/')
        if subreddit.lower().startswith('r/'):
            subreddit = subreddit[2:]
    if (not subreddit) or any(char.isspace() for char in subreddit):
        return ''
    subreddit = subreddit.strip().strip('/')
    return subreddit


def normalize_channel_name(channel):
    channel = channel.strip()
    channel = re.sub(r'^\s*channel\s*:\s*', '', channel, flags=re.IGNORECASE)
    match = _CHANNEL_URL_RE.search(channel)
    if match:
        channel = match.group(1)
    channel = channel.strip().strip('/')
    if channel.startswith('@'):
        channel = channel[1:]
    if (not channel) or any(char.isspace() for char in channel):
        return ''
    return channel


def normalize_tags(tags):
    tags = tags.strip()
    tags = re.sub(r'^\s*tags\s*:\s*', '', tags, flags=re.IGNORECASE)
    normalized = []
    seen = set()
    for raw_part in re.split(r'[\s,]+', tags):
        part = raw_part.strip()
        if not part:
            continue
        if not part.startswith('#'):
            part = '#' + part.lstrip('#')
        if part not in seen:
            normalized.append(part)
            seen.add(part)
    return ' '.join(normalized)


def _build_channel_details(channel, **kwargs):
    normalized_channel = normalize_channel_name(channel)
    normalized_subreddit = normalize_subreddit_name(kwargs['subreddit'])
    normalized_tags = normalize_tags(kwargs['tags'])
    return {
        'submodule': normalized_channel.lower(),
        'channel': '@' + normalized_channel,
        'subreddit': normalized_subreddit,
        'tags': normalized_tags,
        'min_upvotes_limit': kwargs.get('min_upvotes_limit', None),
        'submissions_ranking': kwargs.get('submissions_ranking', 'hot'),
        'submissions_limit': kwargs.get('submissions_limit', 100)
    }


def set_new_channel(channel, **kwargs):
    channels = _get_channels_collection()
    details = _build_channel_details(channel, **kwargs)
    is_any = channels.find_one({'submodule': details['submodule']})
    if is_any is not None:
        return
    channels.insert_one(details)


def upsert_channel(channel, **kwargs):
    channels = _get_channels_collection()
    details = _build_channel_details(channel, **kwargs)
    channels.update_one(
        {'submodule': details['submodule']},
        {'$set': details},
        upsert=True
    )
    return channels.find_one({'submodule': details['submodule']})


class DefaultChannel(object):
    '''docstring for DefaultChannel'''
    def __init__(self, submodule):
        super(DefaultChannel, self).__init__()
        self.submodule = submodule.lower()
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
        channel_details = get_channel_doc(self.submodule)
        if channel_details is None:
            self.t_channel = 'NO CHANNEL FOUND FOR: self.submodule'
            raise ValueError('No channel found in DB for submodule: {}'.format(self.submodule))
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


def get_tags_for_submodule(submodule_name):
    submodule_name = submodule_name.lower()
    channel_doc = get_channel_doc(submodule_name)
    if channel_doc and channel_doc.get('tags'):
        return channel_doc.get('tags')
    tags_filename = os.path.join('channels', submodule_name, 'tags.txt')
    if os.path.exists(tags_filename):
        with open(tags_filename, 'r') as tags_file:
            return tags_file.read()
    return None
