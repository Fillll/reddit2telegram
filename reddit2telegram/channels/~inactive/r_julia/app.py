#encoding:utf-8

subreddit = 'Julia'
t_channel = '@r_Julia'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
