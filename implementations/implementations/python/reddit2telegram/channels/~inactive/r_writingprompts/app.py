#encoding:utf-8

subreddit = 'WritingPrompts'
t_channel = '@r_WritingPrompts'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
