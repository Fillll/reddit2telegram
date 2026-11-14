#encoding:utf-8

subreddit = 'wtf'
t_channel = '@reddit_wtf'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
