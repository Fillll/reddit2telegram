#encoding:utf-8

subreddit = 'battlecats'
t_channel = '@r_battlecats'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
