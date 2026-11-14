#encoding:utf-8

subreddit = 'me_irl'
t_channel = '@r_me_irl'


def send_post(submission, r2t):
    return r2t.send_simple(submission, check_dups=True,
        text=False,
        gif=True,
        img=True,
        album=True,
        other=False
    )
