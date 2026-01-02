#encoding:utf-8

import pymongo
import yaml

import utils
from utils import SupplyResult
from utils.tech import get_dev_channel, short_sleep


subreddit = 'all'
t_channel = '@r_channels'


SETTING_NAME = 1


def send_post(submission, r2t):
    config_filename = 'configs/prod.yml'
    with open(config_filename) as config_file:
        config = yaml.safe_load(config_file.read())
    settings = pymongo.MongoClient(host=config['db']['host'])[config['db']['name']]['settings']
    settings.ensure_index([('setting', pymongo.ASCENDING)])

    last_update_doc = settings.find_one({
        'setting': SETTING_NAME,
    })

    if last_update_doc is None:
        last_update_doc = {
            'last_update': 0
        }
        settings.insert_one({
            'setting': SETTING_NAME,
            'last_update': 0
        })

    updates = r2t.get_updates(offset=last_update_doc['last_update'])

    last_update = 0
    for update in updates:
        # print(update)
        update = update.to_dict()
        # short_sleep()
        if 'qwerrty' in str(update):
            print(update)
        last_update = update['update_id']
        if 'message' not in update:
            continue
        if 'chat' not in update['message']:
            continue
        if 'text' not in update['message']:
            continue

        # print(update)

        user_id = update['message']['chat']['id']
        if not isinstance(user_id, int) or user_id < 0:
            continue

        message_id = update['message']['message_id']
        r2t.forward_message(chat_id=get_dev_channel(), from_chat_id=user_id, message_id=message_id)
        if int(update['message']['chat']['id']) == int(config['telegram']['papa']):
            # print('>>>>>>>>>>>>>>>>>^^^^^^^^^^^^^^')
            text = update['message']['text']
            lines = text.split('\n')
            if 'please' not in lines[0].lower():
                continue
            new_channel_name = lines[1].split(': ')[-1]
            new_subreddit = lines[2].split('/')[-1]
            new_tags = lines[3].split(': ')[-1]
            utils.channels_stuff.set_new_channel(new_channel_name, subreddit=new_subreddit, tags=new_tags)

    settings.find_one_and_update(
        {
            'setting': SETTING_NAME
        },
        {
            '$set': 
            {
                'last_update': last_update
            }
        }
    )
    # It's not a proper supply, so just stop.
    return SupplyResult.STOP_THIS_SUPPLY
