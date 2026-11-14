#encoding:utf-8

subreddit = 'publicfreakout'
t_channel = '@r_publicfreakout'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
