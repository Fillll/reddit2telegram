#encoding:utf-8

subreddit = 'onejob+softwaregore'
t_channel = '@r_onejob'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
