#encoding:utf-8

subreddit = 'SurrealMemes'
t_channel = '@rSurrealMemes'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
