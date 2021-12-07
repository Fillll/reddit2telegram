#encoding:utf-8

subreddit = 'cricket'
t_channel = '@r_cricket'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
