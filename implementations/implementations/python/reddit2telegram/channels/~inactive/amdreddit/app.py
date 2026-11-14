#encoding:utf-8

subreddit = 'Amd'
t_channel = '@AmdReddit'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
