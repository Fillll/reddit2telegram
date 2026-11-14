#encoding:utf-8

subreddit = 'chessmemes+AnarchyChess'
t_channel = '@chessmemes'


def send_post(submission, r2t):
    return r2t.send_simple(submission, check_dups=True,
        min_upvotes_limit=1,
        text=False,
        gif=True,
        img=True,
        album=True,
        other=False
    )
