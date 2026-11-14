#encoding:utf-8

subreddit = 'ihadastroke'
t_channel = '@r_ihadastroke'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
