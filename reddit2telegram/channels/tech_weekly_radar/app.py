#encoding:utf-8

import random
import time

from utils import SupplyResult
from utils.tech import get_active_period, get_newly_active, get_all_public_channels, get_all_tags
from utils.tech import generate_list_of_channels, get_top_growers_for_last_week, default_ending
from utils.tech import chunker


subreddit = 'all'
t_channel = '@reddit2telegram'


def send_post(submission, r2t):
    channels_list = get_all_public_channels(r2t)
    newly_active = get_newly_active(r2t, channels_list)
    top_growers = get_top_growers_for_last_week(r2t, channels_list)

    text_to_send = '<b>Weekend news</b>\n\n'
    if len(newly_active) > 0:
        text_to_send += '🎉 Welcome to newly active channels: {channels_list}. 🎈🎈\n\n'.format(channels_list=', '.join(newly_active))
    text_to_send += '🏆 Channel of the week: {channel_name}. Join and enjoy!\n\n'.format(channel_name=random.choice(channels_list))
    if len(top_growers) > 0:
        text_to_send += '🔥 Hottest channels of the week: {channels}.\n\n'.format(channels=', '.join(top_growers))
    list_of_channels = generate_list_of_channels(channels_list, random_permutation=False)
    text_to_send += default_ending()
    r2t.send_text(text_to_send, parse_mode='HTML')
    time.sleep(2)
    text_to_send = '⬇️ All active channels:\n'
    for l in chunker(list_of_channels, 100):
        text_to_send += '\n'.join(l)
        r2t.send_text(text_to_send)
        text_to_send = ''
        time.sleep(2)
    # Without tags, as it gets annoying
    # text_to_send = '#️⃣ All tags:\n'
    # list_of_tags = list(get_all_tags())
    # # random.shuffle(list_of_tags)
    # text_to_send += ' '.join(sorted(list_of_tags))
    # r2t.send_text(text_to_send, parse_mode='HTML')
    # It's not a proper supply, so just stop.
    return SupplyResult.STOP_THIS_SUPPLY
