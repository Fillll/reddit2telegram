#encoding:utf-8

subreddit = 'tiktokthots'
t_channel = '@r_tiktokthots'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
