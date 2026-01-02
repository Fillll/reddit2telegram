#encoding:utf-8

t_channel = '@dailyfoodporn'
subreddit = 'foodporn'


def send_post(submission, r2t):
    return r2t.send_simple(submission,
        text=False,
        gif=True,
        img=True,
        other=False,
        album=True
    )