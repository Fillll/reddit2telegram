#encoding:utf-8

subreddit = 'nosurf'
t_channel = '@r_nosurf'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
