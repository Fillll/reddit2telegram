#encoding:utf-8

subreddit = 'gog'
t_channel = '@GOGReddit'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
