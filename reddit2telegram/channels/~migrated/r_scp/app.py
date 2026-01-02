#encoding:utf-8

subreddit = 'SCP'
t_channel = '@r_scp'


def send_post(submission, r2t):
    return r2t.send_simple(submission, min_upvotes_limit=50)
