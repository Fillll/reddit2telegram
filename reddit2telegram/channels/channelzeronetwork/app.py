#encoding:utf-8

subreddit = 'ChannelZeroNetwork'
t_channel = '@ChannelZeroNetwork'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
