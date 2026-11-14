#encoding:utf-8

subreddit = 'dankmemes'
t_channel = '@r_dankmemes'


def send_post(submission, r2t):
    return r2t.send_simple(submission, check_dups=True,
        text=False,
        gif=True,
        img=True,
        album=False,
        other=False
    )
