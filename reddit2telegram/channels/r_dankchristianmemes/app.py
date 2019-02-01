#encoding:utf-8

subreddit = 'dankchristianmemes'
t_channel = '@r_dankchristianmemes'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
