#encoding:utf-8

subreddit = 'xboxone'
t_channel = '@r_xboxone'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
