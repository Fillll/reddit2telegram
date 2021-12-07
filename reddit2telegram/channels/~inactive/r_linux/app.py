#encoding:utf-8

subreddit = 'linux'
t_channel = '@r_linux'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
