#encoding:utf-8

subreddit = 'memes'
t_channel = '@MyMemesHQ'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
