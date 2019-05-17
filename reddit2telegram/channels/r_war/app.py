#encoding:utf-8

from utils import weighted_random_subreddit


t_channel = '@r_war'
subreddit = weighted_random_subreddit({
    'combatfootage': 1,
    'ww2': 1,
    'wwiipics': 1,
    'WarshipPorn': 1,
    'MilitaryGifs': 1,
    'battlegifs': 1,
    'tankporn': 1
})


def send_post(submission, r2t):
    return r2t.send_simple(submission,
        text=False,
        gif=True,
        img=True,
        other=False,
        album=True
    )
