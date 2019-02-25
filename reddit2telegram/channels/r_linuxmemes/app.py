#encoding:utf-8

subreddit = 'linuxmemes'
t_channel = '@r_linuxmemes'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
