#encoding:utf-8

subreddit = 'pics'
t_channel = '@r_pics_redux'


def send_post(submission, r2t):
    return r2t.send_simple(submission,
        text=False,
        gif=False,
        img='{title}\n{short_link}',
        album=False,
        other=False
    )
