#encoding:utf-8

subreddit = 'learnprogramming'
t_channel = '@r_learnprogramming'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
