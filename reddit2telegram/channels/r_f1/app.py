#encoding:utf-8

subreddit = 'formula1'
# This is for your public telegram channel.
t_channel = '@r_formula1'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
