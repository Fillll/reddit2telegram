#encoding:utf-8

subreddit = 'wtf+awwwtf'
t_channel = '@WTF_PICTURES'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
