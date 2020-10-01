#encoding:utf-8

subreddit = 'Genshin_Impact'
t_channel = '@Genshin_Impact_reddit'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
