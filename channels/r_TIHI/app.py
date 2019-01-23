from utils import get_url
from utils import SupplyResult

subreddit = 'TIHI'
t_channel = '@r_TIHI'

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
