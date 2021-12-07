#encoding:utf-8

subreddit = 'funnystories'
t_channel = '@r_funnystories'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
