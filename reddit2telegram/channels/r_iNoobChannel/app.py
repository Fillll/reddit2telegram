#encoding:utf-8

subreddit = 'iNoobChannel'
t_channel = '@r_iNoobChannel'


def send_post(submission, r2t):
    return r2t.send_simple(submission,
        text=True,
        gif=True,
        img=True,
        album=True,
        other=False
    )
