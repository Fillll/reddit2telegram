#encoding:utf-8

subreddit = 'nocontextpics'
t_channel = '@r_nocontextpics'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
