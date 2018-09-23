#encoding:utf-8

subreddit = 'mildlyinteresting'
# This is for your public telegram channel.
t_channel = '@r_mild'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
