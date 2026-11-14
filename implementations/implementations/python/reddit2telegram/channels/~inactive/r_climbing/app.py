#encoding:utf-8

subreddit = 'climbing'
t_channel = '@r_climbing'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
