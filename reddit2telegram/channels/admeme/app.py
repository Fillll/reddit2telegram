#encoding:utf-8

subreddit = 'dankmemes+me_irl+memes+greentext'
t_channel = '@admeme'


def send_post(submission, r2t):
    return r2t.send_simple(submission,
        gif='{channel}',
        img='{channel}'
    )
