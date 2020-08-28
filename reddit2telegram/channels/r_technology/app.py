#encoding:utf-8

subreddit = 'technology'
t_channel = '@r_technology'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
