#encoding:utf-8

subreddit = 'PoliticalHumor'
t_channel = '@PoliticalHumor'


def send_post(submission, r2t):
    return r2t.send_simple(submission, check_dups=True,
        text=False,
        gif=True,
        img=True,
        album=True,
        other=False
    )
