#encoding:utf-8

subreddit = 'nosleep'
t_channel = '@rnosleep'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
