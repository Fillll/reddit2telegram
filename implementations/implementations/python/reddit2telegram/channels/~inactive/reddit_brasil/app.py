#encoding:utf-8

subreddit = 'brasil'
t_channel = '@reddit_brasil'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
