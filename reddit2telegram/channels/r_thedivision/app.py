#encoding:utf-8

from utils import weighted_random_subreddit

subreddit = weighted_random_subreddit({
    'thedivision': 1.0,
})
t_channel = '@r_thedivision'

def send_post(submission, r2t):
    return r2t.send_simple(submission,
        min_upvotes_limit=20,
        text=True,
        gif=True,
        img=True,
        album=True,
        other=False
    )
