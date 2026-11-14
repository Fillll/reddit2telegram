#encoding:utf-8

subreddit = 'art'
t_channel = '@redditart'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
