#encoding:utf-8

subreddit = 'zig'
t_channel = '@r_zig'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
