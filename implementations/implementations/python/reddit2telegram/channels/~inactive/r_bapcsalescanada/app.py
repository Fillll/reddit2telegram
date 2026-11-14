#encoding:utf-8

subreddit = 'bapcsalescanada'
t_channel = '@r_bapcsalescanada'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
