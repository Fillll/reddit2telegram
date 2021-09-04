#encoding:utf-8

subreddit = 'avatarmemes'
t_channel = '@r_avatar_memes'


def send_post(submission, r2t):
    return r2t.send_simple(submission,
        min_upvotes_limit=10,
        gif=True,
        img=True,
        album=True,
        other=False
    )
