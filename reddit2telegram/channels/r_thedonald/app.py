#encoding:utf-8

subreddit = 'The_Donald'
t_channel = '@r_TheDonald'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
