#encoding:utf-8

subreddit = 'piracy'
t_channel = '@redditpiracy'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
