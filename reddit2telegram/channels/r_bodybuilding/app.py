#encoding:utf-8

subreddit = 'bodybuilding'
t_channel = '@r_bodybuilding'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
