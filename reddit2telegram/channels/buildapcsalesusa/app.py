#encoding:utf-8

subreddit = 'buildapcsales'
t_channel = '@buildapcsalesusa'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
