#encoding:utf-8

subreddit = 'ChapoTrapHouse'
t_channel = '@r_ChapoTrapHouse'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
