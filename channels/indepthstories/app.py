#encoding:utf-8

subreddit = 'indepthstories'
t_channel = '@indepthstories'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
