#encoding:utf-8

subreddit = 'devops'
t_channel = '@r_devops'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
