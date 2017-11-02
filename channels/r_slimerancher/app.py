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
    title = submission.title
    link = submission.shortlink
    text = '{}\n\n{}'.format(title, link)

    if what == 'text':
        punchline = submission.selftext
        text = '{}\n\n{}\n\n\n{}'.format(title, punchline, link)
        return r2t.send_text(text)
    elif what == 'other':
        base_url = submission.url
        text = '{}\n{}\n\n{}'.format(title, base_url, link)
        return r2t.send_text(text)
    elif what == 'album':
        base_url = submission.url
        text = '{}\n{}\n\n{}'.format(title, base_url, link)
        r2t.send_text(text)
        r2t.send_album(url)
        return True
    elif what in ('gif', 'img'):
        return r2t.send_gif_img(what, url, ext, text)
    else:
        return False
