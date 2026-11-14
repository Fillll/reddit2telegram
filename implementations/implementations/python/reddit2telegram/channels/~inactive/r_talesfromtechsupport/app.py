#encoding:utf-8

subreddit = 'talesfromtechsupport'
t_channel = '@r_talesfromtechsupport'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
