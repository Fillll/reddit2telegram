#encoding:utf-8

subreddit = 'dataisbeatiful'
t_channel = '@r_dataisbeatiful'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
