#encoding:utf-8

subreddit = 'historymemes+history_memes+ancient_history_memes+dankhistorymemes'
t_channel = '@redmeme'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
