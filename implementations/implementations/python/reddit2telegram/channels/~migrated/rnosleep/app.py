#encoding:utf-8

subreddit = 'nosleep'
t_channel = '@rnosleep'


def send_post(submission, r2t):
    return r2t.send_simple(submission,
        check_dups=False,
        text='{title}\n\n{self_text}\n\n{channel}',
        other=False,
        album=False,
        gif=False,
        img=False,
        video=False
    )
