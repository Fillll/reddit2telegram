#encoding:utf-8

subreddit = 'EDC'
t_channel = '@r_edc'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
