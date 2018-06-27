#encoding:utf-8

subreddit = 'Saarbrueckerkreis'
t_channel = '@Saarbrueckerkreis'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
