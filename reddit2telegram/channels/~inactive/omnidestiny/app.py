#encoding:utf-8

subreddit = 'Destiny'
t_channel = '@Omnidestiny'


def send_post(submission, r2t):
    return r2t.send_simple(submission, min_upvotes_limit=150)
