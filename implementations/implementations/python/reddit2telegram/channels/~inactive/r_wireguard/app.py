#encoding:utf-8

subreddit = 'wireguard'
t_channel = '@r_wireguard'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
