#encoding:utf-8

subreddit = 'MapPorn'
t_channel = '@r_mapporn'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
