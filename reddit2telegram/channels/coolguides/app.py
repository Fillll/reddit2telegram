#encoding:utf-8

subreddit = 'coolguides'
t_channel = '@coolguides'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
