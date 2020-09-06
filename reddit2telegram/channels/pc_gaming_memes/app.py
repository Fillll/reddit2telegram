#encoding:utf-8

subreddit = 'gaming'
t_channel = '@pc_gaming_memes'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
