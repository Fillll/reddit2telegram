#encoding:utf-8

subreddit = 'aviation'
t_channel = '@r_aviation'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
