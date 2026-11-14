#encoding:utf-8

subreddit = 'Programming'
t_channel = '@programmingreddit'


def send_post(submission, r2t):
    return r2t.send_simple(submission, min_upvotes_limit=100)
