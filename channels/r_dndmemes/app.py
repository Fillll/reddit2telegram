#encoding:utf-8

subreddit = 'dndmemes+DMDadjokes'
t_channel = '@r_dndmemes'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
