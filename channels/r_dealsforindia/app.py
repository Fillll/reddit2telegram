#kaiz: 1
from .model import Subreddit

subreddit = 'dealsforindia'
t_channel = '@r_dealsforindia'

def send_post(submission, r2t):
    return r2t.send_simple(submission,
        min_upvotes_limit=1,
        text=True,
        gif=True,
        img=True,
        album=True,
        other=True
    )
