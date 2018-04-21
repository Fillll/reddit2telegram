#encoding:utf-8

from utils import get_url


t_channel = '@MaybeMaybeMaybe'
subreddit = 'MaybeMaybeMaybe'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
