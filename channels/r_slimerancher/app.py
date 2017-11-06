#encoding:utf-8

from utils import get_url


# Subreddit that will be a source of content
subreddit = 'slimerancher'
# Telegram channel with @reddit2telegram_bot as an admin
t_channel = '@r_slimerancher'


def send_post(submission, r2t):
    what, url, ext = get_url(submission)

    # If this func returns:
    # False – it means that we will not send
    # this submission, let's move to the next.
    # True – everything is ok, we send the submission
    # None – we do not want to send anything this time,
    # let's just sleep.

    # Get all data from submission that we need
    title = submission.title # Tilte of the submission
    punchline = submission.selftext # Text content of the submission (not always)
    link = submission.shortlink # Link of the submission (not always)
    base_url = submission.url # Reddit link to the submission

    # Create a text for a tg post
    # Base text (for every case)
    text = title + "\n\n"

    # Add text content if exists
    if punchline: # is not None or Empty
        text += punchline + "\n\n"

    # Add link if exists
    if link: # is not None or Empty
        text += link + "\n\n"

    # Add another new line if there is a text content or a link
    if punchline or link: # is not None or Empty
        text += "\n"

    # Base text (for every case)
    # text += base_url

    # How to send a post
    if what == 'text':
        return r2t.send_text(text) # returns True
    elif what == 'other':
        return r2t.send_text(text) # returns True
    elif what == 'album':
        r2t.send_text(text)
        r2t.send_album(url)
        return True
    elif what in ('gif', 'img'):
        return r2t.send_gif_img(what, url, ext, text) # returns True
    else:
        return False
