#encoding:utf-8

subreddit = 'IndianSocial'
t_channel = '@r_IndianSocial'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
