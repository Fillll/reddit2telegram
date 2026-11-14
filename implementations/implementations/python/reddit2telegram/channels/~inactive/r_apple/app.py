#encoding:utf-8

subreddit = 'apple'
t_channel = '@r_apple'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
