#encoding:utf-8

subreddit = 'WANDAVISION'
t_channel = '@WandaVision_reddit'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
