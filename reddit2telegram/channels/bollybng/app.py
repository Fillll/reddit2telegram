#encoding:utf-8

subreddit = 'BollyBlindsNGossip'
t_channel = '@bollybng'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
