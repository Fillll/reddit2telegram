#encoding:utf-8

# Some utils can be useful.
from utils import get_url


# Write here subreddit name. Like this one for /r/jokes.
subreddit = 'gifs'
# This is for your public telegram channel.
t_channel = '@GIFFFs'


def send_post(submission, r2t):
    # Check what is inside this submission.
    what, gif_url, ext = get_url(submission)

    # If inside is something but not text
    # then we do not need this submission.
    if what != 'gif':
        return False

    # To read more about dealing with reddit submission please
    # visit https://praw.readthedocs.io/.
    title = submission.title
    link = submission.shortlink

    # To read more about sending massages to telegram please
    # visit https://github.com/nickoala/telepot/tree/master/examples/simple
    # with simple examples, or visit doc page: http://telepot.readthedocs.io/.
    text = '{}\n@GIFFFs 🤖'.format(title)
    return r2t.send_gif(gif_url, ext, text)
