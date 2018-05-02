#encoding:utf-8

subreddit = 'android'
t_channel = '@reddit_android'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
