#encoding:utf-8

import random

from utils import SupplyResult
from utils.tech import get_active_period, get_newly_active, get_all_public_channels
from utils.tech import generate_list_of_channels, get_top_growers_for_last_week


subreddit = 'all'
t_channel = '@r_channels_test'


def send_post(submission, r2t):
    channels_list = get_all_public_channels()
    newly_active = get_newly_active(r2t, channels_list)
    top_growers = get_top_growers_for_last_week(r2t, channels_list)

    text_to_send = '<b>Weekend news</b>\n\n'
    if len(newly_active) > 0:
        text_to_send += '🎉 Welcome to newly active channels: {channels_list}. 🎈🎈\n\n'.format(channels_list=', '.join(newly_active))
    text_to_send += '🏆 Channel of the week: {channel_name}. Join and enjoy!\n\n'.format(channel_name=random.choice(channels_list))
    if len(top_growers) > 0:
        text_to_send += '🔥 Hottest channels of the week: {channels}.\n\n'.format(channels=', '.join(top_growers))
    list_of_channels = generate_list_of_channels(channels_list, random_permutation=True)
    text_to_send += '⬇️ All active channels:\n{list_of_channels}\n\n'.format(list_of_channels='\n'.join(list_of_channels))
    text_to_send += '🙋\nQ: How can I help?\nA: Promote your favorite channels!\n\n'
    text_to_send += 'Q: How to make similar channels?\nA: Ask here or use manual at https://github.com/Fillll/reddit2telegram.\n\n'
    text_to_send += 'Q: Where to donate?\nA: http://bit.ly/r2t_donate'
    r2t.send_text(text_to_send, parse_mode='HTML')
    # It's not a proper supply, so just stop.
    return SupplyResult.STOP_THIS_SUPPLY
