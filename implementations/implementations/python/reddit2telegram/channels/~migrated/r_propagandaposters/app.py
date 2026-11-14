#encoding:utf-8

from utils import weighted_random_subreddit

subreddit = weighted_random_subreddit({
    'propagandaposters': 1.0,
})

t_channel = '@r_propagandaposters'

def send_post(submission, r2t):
    return r2t.send_simple(submission,
        text=False,
        gif=True,
        img=True,
        album=True,
    )
