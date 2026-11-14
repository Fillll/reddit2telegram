# coding: utf-8

subreddit = 'unexpectedhamilton'
t_channel = '@r_unexpectedhamilton'


def send_post(submission, r2t):
    return r2t.send_simple(
        submission,
        min_upvotes_limit=5,
        check_dups=True,
        text=True,
        gif=True,
        video=True,
        img=True,
        album=True,
        other=False
    )
