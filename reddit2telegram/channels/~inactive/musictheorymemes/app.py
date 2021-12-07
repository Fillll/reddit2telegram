#encoding:utf-8

subreddit = 'musictheorymemes'
t_channel = '@musictheorymemes'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
