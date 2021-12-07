#encoding:utf-8

subreddit = 'selfhosted'
t_channel = '@r_SelfHosted'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
