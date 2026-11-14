#encoding:utf-8

subreddit = 'k12sysadmin'
t_channel = '@r_k12sysadmin'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
