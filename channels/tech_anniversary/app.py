#encoding:utf-8

import time

from utils import SupplyResult
from utils.tech import is_birthday_today, get_all_public_channels


subreddit = 'all'
t_channel = '@r_channels_test'


def send_post(submission, r2t):
    channels_list = get_all_public_channels()

    for channel in channels_list:
        bd_party, years = is_birthday_today(r2t, channel)
        if bd_party:
            time.sleep(10)
            r2t.send_text('{channel} is {years} old.'.format(channel=channel, years=years))
    # It's not a proper supply, so just stop.
    return SupplyResult.STOP_THIS_SUPPLY
