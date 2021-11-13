#encoding:utf-8

from utils import weighted_random_subreddit



subreddit = weighted_random_subreddit({
    'eldenring': 1.0,

})
# Telegram channel with @reddit2telegram_bot as an admin
t_channel = '@r_eldenring'


def send_post(submission, r2t):
    return r2t.send_simple(submission,
        
        min_upvotes_limit=2,
        # If you do not want text submissions, just pass False.
        text=True,
        # If you want gifs, just pass True or text you want under gif.
        gif=True,
        # If you want videos, just pass True or text you want under gif.
        video=True,
        # If you want images, just pass True or text you want under image.
        img=True,
        # If you want albums, just pass True or text you want under albums.
        album=True,
        # If you do not want other submissions, just pass False.
        other=False
    )
