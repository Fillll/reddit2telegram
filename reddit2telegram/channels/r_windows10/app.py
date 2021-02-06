#encoding:utf-8

subreddit = 'Windows10'
t_channel = '@r_Windows10'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
