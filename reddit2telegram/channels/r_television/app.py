#encoding:utf-8

subreddit = 'television'
t_channel = '@r_television'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
