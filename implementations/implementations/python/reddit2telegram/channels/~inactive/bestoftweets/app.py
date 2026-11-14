#encoding:utf-8

subreddit = 'bestoftwitter'
t_channel = '@bestoftweets'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
