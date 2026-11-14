#encoding:utf-8

subreddit = 'thinkpadsforsale'
t_channel = '@r_thinkpadsforsale'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
