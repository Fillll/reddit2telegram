#encoding:utf-8

from utils import weighted_random_subreddit


t_channel = '@rfurryirl'
subreddit = weighted_random_subreddit({
    'furry_irl': 1,
})


def send_post(submission, r2t):
    return r2t.send_simple(submission,
        text=False,
        gif=True,
        img=True,
        other=False,
        album=True
    )
