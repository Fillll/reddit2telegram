#encoding:utf-8

subreddit = 'Intel'
t_channel = '@IntelHQ'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
