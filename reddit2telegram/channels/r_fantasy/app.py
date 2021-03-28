#encoding:utf-8

subreddit = 'fantasy'
t_channel = '@r_fantasy'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
