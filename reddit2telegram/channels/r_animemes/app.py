#encoding:utf-8

subreddit = 'goodanimemes'
t_channel = '@r_Animemes'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
