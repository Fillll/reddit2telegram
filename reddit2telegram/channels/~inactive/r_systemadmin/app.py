#encoding:utf-8

subreddit = 'sysadmin'
t_channel = '@r_systemadmin'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
