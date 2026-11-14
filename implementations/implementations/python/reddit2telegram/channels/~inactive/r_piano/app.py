#encoding:utf-8

subreddit = 'piano'
t_channel = '@r_piano'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
