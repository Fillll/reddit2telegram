#encoding:utf-8

from utils import weighted_random_subreddit


# Subreddit that will be a source of content
subreddit = weighted_random_subreddit({
    'rupaulsdragrace': 1.0,
    # If we want get content from several subreddits
    # please provide here 'subreddit': probability
    # 'any_other_subreddit': 0.02
})
# Telegram channel with @reddit2telegram_bot as an admin
t_channel = '@r_rupaulsdragrace'


def send_post(submission, r2t):
    return r2t.send_simple(submission, check_dups=True,
        text=False,
        gif=True,
        img=True,
        album=True,
        other=False
    )
