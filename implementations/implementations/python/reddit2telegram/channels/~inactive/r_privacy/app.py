#encoding:utf-8

subreddit = 'privacy'
t_channel = '@r_privacy'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
