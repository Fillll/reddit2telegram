#encoding:utf-8

subreddit = 'HighQualityGifs'
t_channel = '@r_HighQualityGifs'


def send_post(submission, r2t):
    return r2t.send_simple(submission,
        text=False,
        gif=True,
        img=False,
        album=False,
        other=False
    )
