#encoding:utf-8

subreddit = 'rickandmorty'
t_channel = '@rickandmorty_en'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
