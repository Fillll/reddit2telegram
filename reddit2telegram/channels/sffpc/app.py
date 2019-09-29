#encoding:utf-8

subreddit = 'sffpc'
t_channel = '@sffpc'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
