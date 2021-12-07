#encoding:utf-8

subreddit = 'hearthstone'
t_channel = '@r_hearthstone'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
