#encoding:utf-8

from utils import weighted_random_subreddit


subreddit = weighted_random_subreddit({'greenandpleasant': 1.0,})
t_channel = 'r_greenandpleasant'

def send_post(submission, r2t):
    return r2t.send_simple(submission, 
        min_upvotes_limit=50, 
        text=False,
        gif=True,
        video=True,
        img=True,
        album=True,
        other=False
    )
