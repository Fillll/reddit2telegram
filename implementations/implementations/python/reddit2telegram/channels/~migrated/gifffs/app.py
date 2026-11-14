#encoding:utf-8

# Write here subreddit name. Like this one for /r/jokes.
subreddit = 'gifs'
# This is for your public telegram channel.
t_channel = '@GIFFFs'


def send_post(submission, r2t):
    return r2t.send_simple(submission,
        text=False,
        gif='{title}\n@GIFFFs 🤖',
        img=False,
        album=False,
        other=False
    )
