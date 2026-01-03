#encoding:utf-8

from utils import weighted_random_subreddit

subreddit = 'LeagueOfMemes'
t_channel = '@r_League_Of_Memes'


def send_post(submission, r2t):
    return r2t.send_simple(submission,
        # Submission should have at least min_upvotes_limit upvotes.
        min_upvotes_limit=10,
        # If you want gifs, just pass True or text you want under gif.
        gif=True,
        # If you want images, just pass True or text you want under image.
        img=True,
        # If you want albums, just pass True or text you want under albums.
        album=True,
    )
