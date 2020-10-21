#encoding:utf-8

subreddit = 'etymology'
t_channel = '@r_etymology'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
