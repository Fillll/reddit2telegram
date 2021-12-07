#encoding:utf-8

subreddit = 'haikuOS'
t_channel = '@r_haikuos'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
