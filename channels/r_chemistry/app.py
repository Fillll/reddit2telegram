#encoding:utf-8

subreddit = 'chemistry'
t_channel = '@r_chemistry'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
