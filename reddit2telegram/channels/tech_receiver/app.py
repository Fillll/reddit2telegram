#encoding:utf-8

import pymongo
import yaml

import utils
from utils import SupplyResult
from utils.tech import get_dev_channel


subreddit = 'all'
t_channel = '@r_channels'


LAST_UPDATE_SETTING = 1
STATE_SETTING_PREFIX = 'tech_receiver_state:'


def _load_config():
    config_filename = 'configs/prod.yml'
    with open(config_filename) as config_file:
        return yaml.safe_load(config_file.read())


def _get_settings_collection(config):
    settings = pymongo.MongoClient(host=config['db']['host'])[config['db']['name']]['settings']
    settings.create_index([('setting', pymongo.ASCENDING)], unique=True)
    return settings


def _state_setting_name(user_id):
    return '{}{}'.format(STATE_SETTING_PREFIX, user_id)


def _load_state(settings, user_id):
    state_doc = settings.find_one({'setting': _state_setting_name(user_id)})
    if state_doc is None:
        return None
    return state_doc.get('data')


def _save_state(settings, user_id, data):
    settings.update_one(
        {'setting': _state_setting_name(user_id)},
        {'$set': {'data': data}},
        upsert=True
    )


def _clear_state(settings, user_id):
    settings.delete_one({'setting': _state_setting_name(user_id)})


def _send_reply(user_id, text, config):
    utils.Reddit2TelegramSender(user_id, config).send_text(text)


def _help_text():
    return (
        'Send channel data in one message:\n'
        'subreddit: https://reddit.com/r/example\n'
        'channel: @example_channel\n'
        'tags: #tag1 #tag2 #tag3\n\n'
        'Or send it step by step:\n'
        '1. subreddit\n'
        '2. channel\n'
        '3. tags\n\n'
        'Commands:\n'
        '/newchannel to restart\n'
        '/cancel to clear the current draft'
    )


def _parse_complete_request(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None

    if lines[0].lower() in ('/newchannel', '/start'):
        lines = lines[1:]

    parsed = {}
    for line in lines:
        lowered = line.lower()
        if lowered.startswith('subreddit'):
            parsed['subreddit'] = utils.channels_stuff.normalize_subreddit_name(line)
        elif lowered.startswith('channel'):
            parsed['channel'] = utils.channels_stuff.normalize_channel_name(line)
        elif lowered.startswith('tags'):
            parsed['tags'] = utils.channels_stuff.normalize_tags(line)

    if all(parsed.get(key) for key in ('subreddit', 'channel', 'tags')):
        return parsed

    if len(lines) == 3:
        subreddit_name = utils.channels_stuff.normalize_subreddit_name(lines[0])
        channel_name = utils.channels_stuff.normalize_channel_name(lines[1])
        tags = utils.channels_stuff.normalize_tags(lines[2])
        if subreddit_name and channel_name and tags:
            return {
                'subreddit': subreddit_name,
                'channel': channel_name,
                'tags': tags,
            }
    return None


def process_message(text, user_id, settings, config, send_reply=None):
    if send_reply is None:
        send_reply = lambda target_user_id, reply_text: _send_reply(target_user_id, reply_text, config)

    stripped_text = text.strip()
    lowered = stripped_text.lower()

    if lowered in ('/help', 'help'):
        send_reply(user_id, _help_text())
        return

    if lowered in ('/cancel', 'cancel'):
        _clear_state(settings, user_id)
        send_reply(user_id, 'Draft cleared.')
        return

    if lowered in ('/newchannel', '/start'):
        _clear_state(settings, user_id)
        _save_state(settings, user_id, {'step': 'await_subreddit'})
        send_reply(user_id, 'Send subreddit name or Reddit URL.')
        return

    complete_request = _parse_complete_request(stripped_text)
    if complete_request is not None:
        existing = utils.channels_stuff.get_channel_doc(complete_request['channel'])
        utils.channels_stuff.upsert_channel(
            complete_request['channel'],
            subreddit=complete_request['subreddit'],
            tags=complete_request['tags'],
        )
        _clear_state(settings, user_id)
        action = 'Updated' if existing is not None else 'Saved'
        send_reply(
            user_id,
            '{} channel:\nsubreddit: r/{}\nchannel: @{}\ntags: {}'.format(
                action,
                complete_request['subreddit'],
                complete_request['channel'],
                complete_request['tags'],
            )
        )
        return

    state = _load_state(settings, user_id)
    if state is None:
        state = {'step': 'await_subreddit'}

    if state['step'] == 'await_subreddit':
        subreddit_name = utils.channels_stuff.normalize_subreddit_name(stripped_text)
        if not subreddit_name:
            send_reply(user_id, _help_text())
            return
        _save_state(settings, user_id, {
            'step': 'await_channel',
            'subreddit': subreddit_name,
        })
        send_reply(user_id, 'Saved subreddit: r/{}\nNow send channel (@name or t.me link).'.format(subreddit_name))
        return

    if state['step'] == 'await_channel':
        channel_name = utils.channels_stuff.normalize_channel_name(stripped_text)
        if not channel_name:
            send_reply(user_id, 'Channel is invalid. Send @channel_name or https://t.me/channel_name')
            return
        state['step'] = 'await_tags'
        state['channel'] = channel_name
        _save_state(settings, user_id, state)
        send_reply(user_id, 'Saved channel: @{}\nNow send tags like #tag1 #tag2 #tag3'.format(channel_name))
        return

    if state['step'] == 'await_tags':
        tags = utils.channels_stuff.normalize_tags(stripped_text)
        if not tags:
            send_reply(user_id, 'Tags are invalid. Send tags like #tag1 #tag2 #tag3')
            return
        existing = utils.channels_stuff.get_channel_doc(state['channel'])
        utils.channels_stuff.upsert_channel(
            state['channel'],
            subreddit=state['subreddit'],
            tags=tags,
        )
        _clear_state(settings, user_id)
        action = 'Updated' if existing is not None else 'Saved'
        send_reply(
            user_id,
            '{} channel:\nsubreddit: r/{}\nchannel: @{}\ntags: {}'.format(
                action,
                state['subreddit'],
                state['channel'],
                tags,
            )
        )
        return

    _clear_state(settings, user_id)
    send_reply(user_id, _help_text())


def send_post(submission, r2t):
    config = _load_config()
    settings = _get_settings_collection(config)

    last_update_doc = settings.find_one({'setting': LAST_UPDATE_SETTING})
    if last_update_doc is None:
        last_update_doc = {'last_update': 0}
        settings.insert_one({
            'setting': LAST_UPDATE_SETTING,
            'last_update': 0
        })

    last_update = last_update_doc['last_update']
    updates = r2t.get_updates(offset=last_update + 1)

    for update in updates:
        update = update.to_dict()
        last_update = max(last_update, update['update_id'])
        if 'message' not in update:
            continue
        if 'chat' not in update['message']:
            continue
        if 'text' not in update['message']:
            continue

        user_id = update['message']['chat']['id']
        if not isinstance(user_id, int) or user_id < 0:
            continue

        message_id = update['message']['message_id']
        r2t.forward_message(chat_id=get_dev_channel(), from_chat_id=user_id, message_id=message_id)
        if int(user_id) == int(config['telegram']['papa']):
            process_message(update['message']['text'], user_id, settings, config)

    settings.find_one_and_update(
        {
            'setting': LAST_UPDATE_SETTING
        },
        {
            '$set':
            {
                'last_update': last_update
            }
        }
    )
    return SupplyResult.STOP_THIS_SUPPLY
