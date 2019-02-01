#encoding:utf-8

from utils import weighted_random_subreddit


t_channel = '@r_bitcoin'
subreddit = weighted_random_subreddit({
    'btc': 0.0,
    'bitcoin': 1.0
})


def send_post(submission, r2t):
    return r2t.send_simple(submission)
