#encoding:utf-8

subreddit = 'dreamcatcher'
t_channel = '@Dreamcatcher_reddit'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
