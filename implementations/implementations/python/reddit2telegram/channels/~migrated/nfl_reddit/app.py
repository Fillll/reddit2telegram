#encoding:utf-8

subreddit = 'nfl'
t_channel = '@NFL_reddit'


def send_post(submission, r2t):
    return r2t.send_simple(submission, min_upvotes_limit=100, check_dups=True)
