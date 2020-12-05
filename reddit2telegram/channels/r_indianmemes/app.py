#encoding:utf-8

subreddit = 'IndianMeyMeys+IndianDankMemes+desimemes+TheRawKnee'
t_channel = '@r_indianmemes'


def send_post(submission, r2t):
    return r2t.send_simple(submission,
    	text=False,
        gif=False,
        img=True,
        album=False,
        other=False
    )
