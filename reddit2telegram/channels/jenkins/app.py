#encoding:utf-8

subreddit = 'jenkins'
t_channel = '@r_jenkins'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
