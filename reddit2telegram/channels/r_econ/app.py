#encoding:utf-8

subreddit = 'econpapers+economics+economy'
t_channel = '@r_econ'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
