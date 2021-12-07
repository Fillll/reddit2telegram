#encoding:utf-8

subreddit = 'videomemes'
t_channel = '@r_videomemes'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
