#encoding:utf-8

from pprint import pprint
import time

import pymongo
import yaml

from utils import SupplyResult
from utils.tech import get_dev_channel


subreddit = 'all'
t_channel = '@r_channels'


def send_post(submission, r2t):
    config_filename = 'configs/prod.yml'
    with open(config_filename) as config_file:
        config = yaml.load(config_file.read())
    settings = pymongo.MongoClient(host=config['db']['host'])[config['db']['name']]['settings']

    last_update_doc = settings.find_one({
        'settings': 1,
    })

    if last_update_doc is None:
        last_update_doc = {
            'last_update': 0
        }

    updates = r2t.telepot_bot.getUpdates(offset=last_update_doc['last_update'])

    last_update = 0
    for update in updates:
        # pprint(update)
        time.sleep(2)
        last_update = update['update_id']

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
        r2t.telepot_bot.forwardMessage(chat_id=get_dev_channel(), from_chat_id=user_id, message_id=message_id)

    settings.find_one_and_update(
        {
            'settings': 1
        },
        {
            "$set": 
            {
                'last_update': last_update + 1
            }
        }
    )
    # It's not a proper supply, so just stop.
    return SupplyResult.STOP_THIS_SUPPLY
