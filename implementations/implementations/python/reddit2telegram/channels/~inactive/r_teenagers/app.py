#encoding:utf-8

subreddit = 'teenagers'
t_channel = '@r_teenagers'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
