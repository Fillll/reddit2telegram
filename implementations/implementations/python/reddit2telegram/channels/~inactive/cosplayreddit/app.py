#encoding:utf-8

subreddit = 'cosplay'
t_channel = '@CosplayReddit'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
