#encoding:utf-8

subreddit = 'QtFramework'
t_channel = '@qt_reddit'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
