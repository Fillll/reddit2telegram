#encoding:utf-8

subreddit = 'Awwducational'
t_channel = '@Awwducational'


def send_post(submission, r2t):
    return r2t.send_simple(submission,
    	gif='{title}\n\n{self_text}',
        img='{title}\n\n{self_text}',
        album=False,
        text=False,
        other=False
    )
