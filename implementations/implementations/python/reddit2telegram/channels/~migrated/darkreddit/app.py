#encoding:utf-8

subreddit = 'darkjokes'
t_channel = '@darkreddit'


def send_post(submission, r2t):
    return r2t.send_simple(submission, min_upvotes_limit=30)
