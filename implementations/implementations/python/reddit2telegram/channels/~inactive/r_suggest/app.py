#encoding:utf-8

subreddit = 'suggestmeabook'
t_channel = '@r_suggest'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
