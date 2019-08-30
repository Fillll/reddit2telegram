#encoding:utf-8

subreddit = 'youshouldknow'
t_channel = '@r_youshouldknow'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
