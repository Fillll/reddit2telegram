#encoding:utf-8


from utils import SupplyResult
from utils.tech import is_birthday_today, get_all_public_channels, get_dev_channel
from utils.tech import generate_list_of_channels, default_ending, chunker
from utils.tech import short_sleep, long_sleep
from suplier import send_to_channel_from_subreddit
from channels.reddit2telegram.app import make_nice_submission


subreddit = 'all'
t_channel = get_dev_channel()


def send_post(submission, r2t):
    channels_list = get_all_public_channels(r2t)

    for channel in channels_list:
        bd_party, years = is_birthday_today(r2t, channel)
        if bd_party and years > 0:
            plural = 's' if years != 1 else ''
            # To the @r_channels
            long_sleep()
            r2t.t_channel = '@r_channels'
            cakes = '🎂' * years
            text_to_send = '{cake}\n🎁 Today {channel} is {years_cnt} year{s} old.\n🎉 Congratulations! 🎈'.format(
                channel=channel,
                years_cnt=years,
                s=plural,
                cake=cakes
            )
            r2t.send_text(text_to_send)
            # To the dev channel
            long_sleep()
            r2t.t_channel = get_dev_channel()
            r2t.send_text(text_to_send)
            # To the channels itself
            long_sleep()
            r2t.t_channel = channel
            text1_to_send = text_to_send
            list_of_channels = generate_list_of_channels(channels_list, random_permutation=True)
            text3_to_send = default_ending()
            r2t.send_text(text1_to_send)
            short_sleep()
            text2_to_send = 'Other @reddit2telegram channels powered by @r_channels:\n'
            for l in chunker(list_of_channels, 100):
                text2_to_send += '\n'.join(l)
                r2t.send_text(text2_to_send)
                text2_to_send = ''
                short_sleep()
            r2t.send_text(text3_to_send)
            long_sleep()
            # send_to_channel_from_subreddit(
            #     how_to_post=make_nice_submission,
            #     channel_to_post='@reddit2telegram',
            #     subreddit=submodule.subreddit,
            #     submissions_ranking=submissions_ranking,
            #     submissions_limit=submissions_limit,
            #     config=config,
            #     extra_args_in_text=False
            # )
    # It's not a proper supply, so just stop.
    return SupplyResult.STOP_THIS_SUPPLY
