#encoding:utf-8

subreddit = 'hololive'
t_channel = '@r_hololive'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
