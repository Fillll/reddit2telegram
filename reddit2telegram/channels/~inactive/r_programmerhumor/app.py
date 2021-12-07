#encoding:utf-8

subreddit = 'programmerhumor'
t_channel = '@r_programmerhumor'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
