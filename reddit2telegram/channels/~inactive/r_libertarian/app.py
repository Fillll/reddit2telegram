#encoding:utf-8

subreddit = 'libertarian'
t_channel = '@r_libertarian'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
