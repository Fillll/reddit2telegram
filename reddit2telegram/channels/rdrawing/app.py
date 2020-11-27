#encoding:utf-8

subreddit = 'drawing'
t_channel = '@rdrawing'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
