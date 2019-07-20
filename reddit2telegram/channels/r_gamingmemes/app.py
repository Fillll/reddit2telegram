#encoding:utf-8

subreddit = 'gamingmemes+gamememes+Gaming_Memes+gaming'
t_channel = '@r_gamingmemes'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
