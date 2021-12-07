#encoding:utf-8

subreddit = 'WikiLeaks'
t_channel = '@r_WikiLeaks'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
