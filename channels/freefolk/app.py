#encoding:utf-8

t_channel = '@r_freefolk'
subreddit = 'freefolk'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
