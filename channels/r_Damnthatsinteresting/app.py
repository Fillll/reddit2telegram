#encoding:utf-8

# Some utils can be useful.
from utils import get_url


# Write here subreddit name. Like this one for /r/Damnthatsinteresting.
subreddit = 'Damnthatsinteresting'
# This is for your public telegram channel.
t_channel = '@r_Damnthatsinteresting'


def send_post(submission, r2t):
    # Check what is inside this submission.
    what, _, _ = get_url(submission)

    # If inside is something but not text
    # then we do not need this submission.
    if what != 'text':
        False

    # To read more about dealing with reddit submission please
    # visit https://praw.readthedocs.io/.
    title = submission.title
    punchline = submission.selftext
    link = submission.shortlink
    text = '{title}\n\n{body}\n\n{link}\n{channel}'.format(
            title=title, body=punchline, link=link, channel=t_channel)

    # Long jokes are weired.
    if len(text) > 3456:
        return False

    # To read more about sending massages to telegram please
    # visit https://github.com/nickoala/telepot/tree/master/examples/simple
    # with simple examples, or visit doc page: http://telepot.readthedocs.io/.
    r2t.send_text(text, disable_web_page_preview=True)

    # Return True, if this submission is suitable for sending and was sent,
    # if not – return False.
    return True
