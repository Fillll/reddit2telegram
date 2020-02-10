#encoding:utf-8

subreddit = 'animegifs'
t_channel = '@r_animegifs'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
