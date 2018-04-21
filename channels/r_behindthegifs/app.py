#encoding:utf-8

subreddit = 'behindthegifs'
t_channel = '@r_behindthegifs'


def send_post(submission, r2t):
    return r2t.send_simple(submission,
        text=False,
        gif=False,
        img=False,
        album=True,
        other=False
    )