#encoding:utf-8

subreddit = 'darkfunny'
t_channel = '@r_dark_humor'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
