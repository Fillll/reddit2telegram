#encoding:utf-8

subreddit = 'vinyl'
t_channel = '@r_vinyl'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
