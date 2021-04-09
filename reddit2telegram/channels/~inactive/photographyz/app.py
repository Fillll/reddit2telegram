#encoding:utf-8

subreddit = 'photography'
t_channel = '@photographyz'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
