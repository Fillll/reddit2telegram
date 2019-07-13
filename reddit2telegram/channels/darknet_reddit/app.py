#encoding:utf-8

subreddit = 'onions+darknet+IntelligenceNews+threatIntel+i2p'
t_channel = '@darknet_reddit'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
