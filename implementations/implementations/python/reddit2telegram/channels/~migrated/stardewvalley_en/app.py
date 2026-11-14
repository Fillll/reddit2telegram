#encoding:utf-8

subreddit = 'StardewValley+StardewMemes'
t_channel = '@stardewvalley_en'

def send_post(submission, r2t):
    return r2t.send_simple(
        submission,
        text=True,
        gif=True,
        video=True,
        img=True,
        album=True,
        other=False
    )