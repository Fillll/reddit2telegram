#encoding:utf-8

subreddit = 'nosafetysmokingfirst'
t_channel = '@r_nosafetysmokingfirst'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
