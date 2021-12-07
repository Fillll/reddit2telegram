#encoding:utf-8

subreddit = 'fightporn'
t_channel = '@fights1'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
