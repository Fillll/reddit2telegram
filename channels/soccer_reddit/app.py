#encoding:utf-8

subreddit = 'soccer'
t_channel = '@soccer_reddit'


def send_post(submission, r2t):
    return r2t.send_simple(submission, min_upvotes_limit=100, check_dups=True)
