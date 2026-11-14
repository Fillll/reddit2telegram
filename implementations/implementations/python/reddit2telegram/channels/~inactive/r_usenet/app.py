#encoding:utf-8

subreddit = 'usenet'
t_channel = '@r_usenet'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
