#encoding:utf-8

subreddit = 'shitposters_paradise'
t_channel = '@r_shitposters_paradise'


def send_post(submission, r2t):
    return r2t.send_simple(submission, check_dups=True,
        text=False,
        gif=True,
        img=True,
        album=False,
        other=False
    )
