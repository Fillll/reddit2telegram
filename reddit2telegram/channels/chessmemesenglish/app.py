#encoding:utf-8

subreddit = 'chessmemes'
t_channel = '@chessmemesenglish'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
