#encoding:utf-8

subreddit = 'Designporn'
t_channel = '@r_designporn'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
