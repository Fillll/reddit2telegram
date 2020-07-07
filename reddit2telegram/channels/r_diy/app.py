#encoding:utf-8

subreddit = 'DIY'
t_channel = '@r_diy'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
