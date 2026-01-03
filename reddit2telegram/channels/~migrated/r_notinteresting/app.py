# coding: utf-8

subreddit = 'notinteresting'
t_channel = '@r_notinteresting'


def send_post(submission, r2t):
    return r2t.send_simple(
        submission,
        check_dups=True,
        text=False,
        gif=True,
        img=True,
        album=True,
        other=False
    )
