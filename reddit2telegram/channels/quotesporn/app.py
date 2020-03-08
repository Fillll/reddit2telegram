#encoding:utf-8

subreddit = 'quotes+quotesporn'
t_channel = '@quotesporn'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
