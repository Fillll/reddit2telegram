#encoding:utf-8

import time

from utils import SupplyResult
from utils.tech import is_birthday_today, get_all_public_channels, get_dev_channel
from utils.tech import generate_list_of_channels, default_ending


subreddit = 'all'
t_channel = get_dev_channel()


def send_post(submission, r2t):
    channels_list = get_all_public_channels(r2t)

    for channel in channels_list:
        bd_party, years = is_birthday_today(r2t, channel)
        if bd_party and years > 0:
            plural = 's' if years != 1 else ''
            # To the @r_channels
            time.sleep(10)
            r2t.t_channel = '@r_channels'
            text_to_send = '🎂🎂🎂\nToday {channel} is {years_cnt} year{s} old.\nCongratulations! 🎁'.format(
                channel=channel, years_cnt=years, s=plural)
            r2t.send_text(text_to_send)
            # To the dev channel
            time.sleep(10)
            r2t.t_channel = get_dev_channel()
            r2t.send_text(text_to_send)
            # To the channels itself
            time.sleep(10)
            r2t.t_channel = channel
            text1_to_send = '🎂🎂🎂\nToday {channel} is {years_cnt} year{s} old. '.format(
                channel=channel, years_cnt=years, s=plural)
            text1_to_send += 'Congratulations! 🎈🎉🎉\n\n'
            list_of_channels = generate_list_of_channels(channels_list, random_permutation=True)
            text2_to_send = 'Other @reddit2telegram channels powered by @r_channels:\n{list_of_channels}\n\n'.format(
                list_of_channels='\n'.join(list_of_channels))
            text3_to_send = default_ending()
            r2t.send_text(text1_to_send)
            time.sleep(2)
            r2t.send_text(text2_to_send)
            time.sleep(2)
            r2t.send_text(text3_to_send)
            # To the dev channel again
            time.sleep(10)
            r2t.t_channel = get_dev_channel()
            r2t.send_text(text1_to_send)
            time.sleep(2)
            r2t.send_text(text2_to_send)
            time.sleep(2)
            r2t.send_text(text3_to_send)

    # It's not a proper supply, so just stop.
    return SupplyResult.STOP_THIS_SUPPLY
