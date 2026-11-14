#encoding:utf-8

subreddit = 'theydidthemath'
t_channel = '@TheyDidTheMath'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
