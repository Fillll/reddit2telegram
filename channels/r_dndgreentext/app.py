#encoding:utf-8

subreddit = 'dndgreentext'
t_channel = '@r_dndgreentext'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
