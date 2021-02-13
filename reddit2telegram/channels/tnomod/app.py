#encoding:utf-8

from utils import weighted_random_subreddit

subreddit = weighted_random_subreddit({
    'tnomod': 1.0,
    'dsrfunny': 0.2
})

t_channel = '@tnomod'

def send_post(submission, r2t):
    return r2t.send_simple(submission,
    min_upvotes_limit=300,
        text=True,
        gif=True,
        img=True,
        album=True
    )