#encoding:utf-8

subreddit = 'Nikon'
t_channel = '@NikonBackup'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
