#encoding:utf-8

subreddit = 'dota2'
t_channel = '@r_dota2'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
