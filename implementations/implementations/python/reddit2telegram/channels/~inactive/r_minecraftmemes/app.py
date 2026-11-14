#encoding:utf-8

subreddit = 'MinecraftMemes'
t_channel = '@r_MinecraftMemes'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
