#encoding:utf-8

# Some utils can be useful.
from utils import get_url
from utils import SupplyResult


# Write here subreddit name. Like this one for /r/jokes.
subreddit = 'jokes'
# This is for your public telegram channel.
t_channel = '@r_jokes'


def send_post(submission, r2t):
    # Check what is inside this submission.
    what, _, _ = get_url(submission)

    # If inside is something but not text
    # then we do not need this submission.
    if what != 'text':
        return SupplyResult.DO_NOT_WANT_THIS_SUBMISSION

    # If there is not enough upvotes, let's check this submission
    # next time.
    if submission.score < 111:
        return SupplyResult.SKIP_FOR_NOW

    # To read more about dealing with reddit submission please
    # visit https://praw.readthedocs.io/.
    title = submission.title
    punchline = submission.selftext
    link = submission.shortlink
    text = '{title}\n\n{body}\n\n{link}\n{channel}'.format(
            title=title, body=punchline, link=link, channel=t_channel)

    # Long jokes are weired.
    if len(text) > 3210:
        return SupplyResult.DO_NOT_WANT_THIS_SUBMISSION

    # To read more about sending massages to telegram please
    # visit https://github.com/nickoala/telepot/tree/master/examples/simple
    # with simple examples, or visit doc page: http://telepot.readthedocs.io/.

    # Return True, if this submission is suitable for sending and was sent,
    # if not – return False.
    return r2t.send_text(text, disable_web_page_preview=True)
