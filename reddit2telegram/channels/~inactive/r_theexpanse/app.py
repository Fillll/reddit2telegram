#encoding:utf-8

subreddit = 'TheExpanse'
t_channel = '@r_theexpanse'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
