#encoding:utf-8

subreddit = 'softwaregore'
t_channel = '@r_softwaregore'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
