#encoding:utf-8

subreddit = 'PolHumor'
t_channel = '@r_PolHumor'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
