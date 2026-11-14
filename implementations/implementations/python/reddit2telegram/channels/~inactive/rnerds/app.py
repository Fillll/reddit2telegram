#encoding:utf-8

subreddit = 'science'
t_channel = '@rnerds'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
