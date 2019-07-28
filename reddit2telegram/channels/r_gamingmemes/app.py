#encoding:utf-8

subreddit = 'gamingmemes+gamememes+Gaming_Memes+gaming'
t_channel = '@r_gamingmemes'


def send_post(submission, r2t):
    return r2t.send_simple(submission,
        text='{title}\n\n{self_text}\n\n/r/{subreddit_name}\n{channel}',
        other='{title}\n{link}\n\n/r/{subreddit_name}\n{channel}',
        album='{title}\n{link}\n\n/r/{subreddit_name}\n{channel}',
        gif='{title}\n\n/r/{subreddit_name}\n{channel}',
        img='{title}\n\n/r/{subreddit_name}\n{channel}'
    )
