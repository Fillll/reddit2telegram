#encoding:utf-8

subreddit = 'selfie'
t_channel = '@rselfie'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
