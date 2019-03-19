#encoding:utf-8

subreddit = 'ThinkPad'
t_channel = '@r_thinkpad'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
