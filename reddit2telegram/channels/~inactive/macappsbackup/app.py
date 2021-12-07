#encoding:utf-8

subreddit = 'macapps'
t_channel = '@macappsbackup'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
