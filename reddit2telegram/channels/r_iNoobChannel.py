#encoding:utf-8

subreddit = 'iNoobChannel'
t_channel = '@r_iNoobChannel'


def send_post(submission, r2t):
    return r2t.send_simple(submission,
        # If you do not want text submissions, just pass False.
        text=True,
        # If you want gifs, just pass True or text you want under gif.
        gif=True,
        # If you want images, just pass True or text you want under image.
        img=True,
        # If you want albums, just pass True or text you want under albums.
        album=True,
        # If you do not want othe submissions, just pass False.
        other=False
    )
