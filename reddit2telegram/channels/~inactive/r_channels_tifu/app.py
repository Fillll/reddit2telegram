#encoding:utf-8

subreddit = 'tifu'
t_channel = '@r_channels_tifu'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
