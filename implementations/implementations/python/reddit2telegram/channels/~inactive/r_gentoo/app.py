#encoding:utf-8

subreddit = 'gentoo'
t_channel = '@r_gentoo'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
