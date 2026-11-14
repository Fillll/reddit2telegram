#encoding:utf-8

from utils import get_url
from utils import SupplyResult


# Subreddit that will be a source of content
subreddit = 'cursedcomments'
# Telegram channel with @reddit2telegram_bot as an admin
t_channel = '@r_CursedComments'


def send_post(submission, r2t):
    what, url = get_url(submission)

    # If this func returns:
    # False – it means that we will not send
    # this submission, let's move to the next.
    # True – everything is ok, we send the submission
    # None – we do not want to send anything this time,
    # let's just sleep.

    # Get all data from submission that we need
    title = submission.title # Tilte of the submission
    punchline = submission.selftext # Text content of the submission (not always)
    base_url = submission.url # Link of the submission (not always)
    link = submission.shortlink # Reddit link to the submission

    # Create a text for a tg post
    # Base text (for every case)
    text = title + "\n\n"

    # Add text content if exists
    if punchline: # is not None or Empty
        text += punchline + "\n\n"

    # Add link if exists
    if base_url and what == 'other': # base_url is not None or Empty and what is other
        text += base_url + "\n\n"

    # Add another new line if there is a text content or a link
    if punchline or (base_url and what == 'other'): # is not None or Empty
        text += "\n"

    # Base text (for every case)
    text += link

    # How to send a post
    if what == 'text':
        return r2t.send_text(text) # returns True
    elif what == 'other':
        return r2t.send_text(text) # returns True
    elif what == 'album':
        r2t.send_text(text)
        return r2t.send_album(url)
    elif what in ('gif', 'img'):
        return r2t.send_gif_img(what, url, text) # returns True
    else:
        return SupplyResult.DO_NOT_WANT_THIS_SUBMISSION
