#encoding:utf-8

from utils import weighted_random_subreddit


# Subreddit that will be a source of content
subreddit = weighted_random_subreddit({
    'scala': 1.0,
})
t_channel = '@r_scala'


def send_post(submission, r2t):
    return r2t.send_simple(submission,
        min_upvotes_limit=10,
        gif=True,
        video=True,
        img=True,
        album=True,
        gallery=True,
    )
