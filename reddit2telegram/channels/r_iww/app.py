#encoding:utf-8

subreddit = 'iww'
t_channel = '@r_iww'


def send_post(submission, r2t):
    return r2t.send_simple(submission, min_upvotes_limit=10)
