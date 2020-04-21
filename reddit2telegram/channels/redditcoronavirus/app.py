#encoding:utf-8

subreddit = 'Coronavirus+COVID19'
t_channel = '@redditcoronavirus'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
