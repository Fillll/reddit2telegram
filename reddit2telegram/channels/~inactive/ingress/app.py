#encoding:utf-8

subreddit = 'Ingress'
t_channel = '@IngressReddit'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
