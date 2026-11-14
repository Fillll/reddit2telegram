#encoding:utf-8

from utils import weighted_random_subreddit


subreddit = weighted_random_subreddit({
    'borderHands': 1,
    'Borderlands': 1,
    'Borderlands2': 1,
    'borderlands3': 1
})
t_channel = '@r_vault_hunters'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
