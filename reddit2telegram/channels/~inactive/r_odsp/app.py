#encoding:utf-8

subreddit = 'odsp'
t_channel = '@r_ODSP'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
