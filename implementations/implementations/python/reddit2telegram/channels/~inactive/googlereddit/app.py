#encoding:utf-8

subreddit = 'google'
t_channel = '@GoogleReddit'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
