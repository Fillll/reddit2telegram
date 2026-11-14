#encoding:utf-8

subreddit = 'historymemes+fakehistoryporn'
t_channel = '@r_historicalmemes'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
