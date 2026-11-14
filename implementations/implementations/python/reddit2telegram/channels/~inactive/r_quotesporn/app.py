#encoding:utf-8

subreddit = 'Quotesporn'
t_channel = '@r_quotesporn'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
