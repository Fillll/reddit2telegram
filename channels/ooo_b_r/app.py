#encoding:utf-8

from utils import weighted_random_subreddit


# Group chat https://yal.sh/dvdahoy
t_channel = '-1001065558871'
subreddit = weighted_random_subreddit({
    'ANormalDayInRussia': 1.0,
    'ANormalDayInAmerica': 0.1,
    'ANormalDayInJapan': 0.01
})


def send_post(submission, r2t):
    return r2t.send_simple(submission,
        text=False,
        gif='{title}\n{short_link}',
        img='{title}\n{short_link}',
        album=False,
        other=False
    )