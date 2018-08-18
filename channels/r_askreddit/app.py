#encoding:utf-8

t_channel = '@r_AskReddit'
subreddit = 'AskReddit'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
