#encoding:utf-8

subreddit = 'ADHD'
t_channel = '@r_adhd'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
