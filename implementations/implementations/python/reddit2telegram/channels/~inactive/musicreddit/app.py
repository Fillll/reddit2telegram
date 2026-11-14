#encoding:utf-8

subreddit = 'Music'
t_channel = '@MusicReddit'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
