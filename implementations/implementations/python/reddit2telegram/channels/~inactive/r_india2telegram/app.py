#encoding:utf-8

subreddit = 'india'
t_channel = '@r_india2telegram'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
