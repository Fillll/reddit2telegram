#encoding:utf-8

t_channel = '@r_wholesomememes'
subreddit = 'wholesomeMemes+wholesomeAnimemes+wholesomeGifs+wholesomeComics'


def send_post(submission, r2t):
    return r2t.send_simple(submission, check_dups=True,
        text=True,
        gif=True,
        img=True,
        album=True,
        other=False
    )
