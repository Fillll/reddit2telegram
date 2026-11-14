#encoding:utf-8

subreddit = 'comedycemetery'
t_channel = '@r_ComedyCemetery'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
