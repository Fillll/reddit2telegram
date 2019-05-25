#encoding:utf-8

subreddit = 'bakchodi'
t_channel = '@r_bakchodi'


def send_post(submission, r2t):
    return r2t.send_simple(submission, text=False)
