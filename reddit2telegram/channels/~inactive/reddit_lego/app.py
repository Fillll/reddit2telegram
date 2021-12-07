#encoding:utf-8

subreddit = 'lego'
t_channel = '@reddit_lego'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
