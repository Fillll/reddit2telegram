#encoding:utf-8

subreddit = 'Eyebleach'
t_channel = '@get_happiness'


def send_post(submission, r2t):
    return r2t.send_simple(submission,
    	text=False,
        gif=True,
        img=True,
        album=True,
        other=False
    )
