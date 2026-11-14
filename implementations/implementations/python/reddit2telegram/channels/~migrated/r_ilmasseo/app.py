#encoding:utf-8

subreddit = 'IlMasseo'
t_channel = '@r_ilMasseo'


def send_post(submission, r2t):
    return r2t.send_simple(submission,
        text=True,
        gif=True,
        img=True,
        album=True,
        other=False
    )
