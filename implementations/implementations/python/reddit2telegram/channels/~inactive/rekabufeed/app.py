#encoding:utf-8

subreddit = 'pikabu'
t_channel = '@rekabufeed'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
