#encoding:utf-8

subreddit = 'progresspics'
t_channel = '@r_progresspics'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
