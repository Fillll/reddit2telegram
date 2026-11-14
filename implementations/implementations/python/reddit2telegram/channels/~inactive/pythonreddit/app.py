#encoding:utf-8

subreddit = 'python'
t_channel = '@pythonreddit'


def send_post(submission, r2t):
    return r2t.send_simple(submission, min_upvotes_limit=100)
