#encoding:utf-8

subreddit = 'swimsuitasians'
t_channel = '@r_swimsuitasians'


def send_post(submission, r2t):
    return r2t.send_simple(submission,
        min_upvotes_limit=20,
        text=False,
        gif=True,
        video=True,
        img=True,
        album=True,
        other=True
    )
