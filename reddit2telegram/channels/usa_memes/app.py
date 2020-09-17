#encoding:utf-8

subreddit = 'Funny+Gifs'
t_channel = '@USA_MEMES'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
