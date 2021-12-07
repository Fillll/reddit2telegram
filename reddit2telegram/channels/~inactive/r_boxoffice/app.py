#encoding:utf-8

subreddit = 'boxoffice'
t_channel = '@r_boxoffice'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
