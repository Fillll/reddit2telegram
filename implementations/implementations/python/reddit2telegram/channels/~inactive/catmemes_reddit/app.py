#encoding:utf-8

subreddit = 'Catmemes'
t_channel = '@catmemes_reddit'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
