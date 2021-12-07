#encoding:utf-8

subreddit = 'HermitCraft'
t_channel = '@r_HermitCraft'


def send_post(submission, r2t):
    return r2t.send_simple(submission, min_upvotes_limit=100)
