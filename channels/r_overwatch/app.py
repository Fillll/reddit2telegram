#encoding:utf-8

subreddit = 'overwatch'
t_channel = '@r_overwatch'


def send_post(submission, r2t):
    return r2t.send_simple(submission,
        text=False,
        gif=True,
        img=False,
        album=False,
        other=False
    )
