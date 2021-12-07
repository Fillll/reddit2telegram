#encoding:utf-8

subreddit = 'Instagramreality'
t_channel = '@InstaReality'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
