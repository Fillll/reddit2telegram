#encoding:utf-8

subreddit = 'trippinthroughtime'
t_channel = '@classicalartmemes'


def send_post(submission, r2t):
    return r2t.send_simple(submission, img=True)
