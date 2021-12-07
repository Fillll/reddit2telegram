#encoding:utf-8

subreddit = 'AzureLane'
t_channel = '@AzurLane_sub'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
