#encoding:utf-8

subreddit = 'Facepalm'
t_channel = '@facepalmers'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
