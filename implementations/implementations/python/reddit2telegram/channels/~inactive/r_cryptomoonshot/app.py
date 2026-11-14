#encoding:utf-8

subreddit = 'CryptoMoonShots'
t_channel = '@r_CryptoMoonShot'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
