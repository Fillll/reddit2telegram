#encoding:utf-8

subreddit = 'JellesMarbleRuns'
t_channel = '@MarbleRacing'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
