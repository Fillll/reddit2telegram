#encoding:utf-8

t_channel = '@r_wholesomememes'
subreddit = 'WholesomeComics+wholesomeanimemes+wholesomebestof+wholesomegifs+wholesomememes' 


def send_post(submission, r2t):
    return r2t.send_simple(submission, check_dups=True,
        text=True,
        gif=True,
        img=True,
        album=True,
        other=False
    )
