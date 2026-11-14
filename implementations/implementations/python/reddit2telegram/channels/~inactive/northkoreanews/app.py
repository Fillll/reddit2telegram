#encoding:utf-8

subreddit = 'northkoreanews'
t_channel = '@northkoreanews'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
