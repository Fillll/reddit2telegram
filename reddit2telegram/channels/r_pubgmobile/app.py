#encoding:utf-8

from utils import weighted_random_subreddit


# Subreddit that will be a source of content
subreddit = weighted_random_subreddit({
    'funny': 1.0,
    # If we want get content from several subreddits
    # please provide here 'subreddit': probability
    # 'any_other_subreddit': 0.02
})
# Telegram channel with @reddit2telegram_bot as an admin
t_channel = '@r_pubgmobile'


def send_post(submission, r2t):
    return r2t.send_simple(submission,
        # Submission should have at least min_upvotes_limit upvotes.
        min_upvotes_limit=100,
        # If you do not want text submissions, just pass False.
        text=False,
        # If you want gifs, just pass True or text you want under gif.
        gif=True,
        # If you want images, just pass True or text you want under image.
        img=True,
        # If you want albums, just pass True or text you want under albums.
        album=True,
        # If you do not want othe submissions, just pass False.
        other=False
    )
