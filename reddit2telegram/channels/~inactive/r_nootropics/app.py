#encoding:utf-8

subreddit = 'nootropics'
t_channel = '@r_nootropics'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
