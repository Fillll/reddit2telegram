#encoding:utf-8

from utils import weighted_random_subreddit


subreddit = weighted_random_subreddit({
    'WhitePeopleTwitter': 1,
    'BlackPeopleTwitter': 1
})
t_channel = '@AllTwitter'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
