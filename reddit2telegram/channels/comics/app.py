#encoding:utf-8

from utils import get_url, weighted_random_subreddit
from utils import SupplyResult


# Subreddit that will be a source of content
subreddit = weighted_random_subreddit({
    'comics': 1.0,
    # If we want get content from several subreddits
    # please provide here 'subreddit': probability
    # 'any_other_subreddit': 0.02
})
# Telegram channel with @reddit2telegram_bot as an admin
t_channel = '@r_comics'


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
    text = '{}\n{}'.format(title, link)

    if what == 'text':
        # If it is text submission, it is not really funny.
        # return r2t.send_text(submission.selftext)
        return SupplyResult.DO_NOT_WANT_THIS_SUBMISSION
    elif what == 'other':
        # Also we are not interesting in any other content.
        return SupplyResult.DO_NOT_WANT_THIS_SUBMISSION
    elif what == 'album':
        # It is ok if it is an album.
        base_url = submission.url
        text = '{}\n{}\n\n{}'.format(title, base_url, link)
        r2t.send_text(text)
        r2t.send_album(url)
        return SupplyResult.SUCCESSFULLY
    elif what in ('gif', 'img'):
        # Also it is ok if it is gif or any kind of image.

        # Check if content has already appeared in
        # out telegram channel.
        if r2t.dup_check_and_mark(url) is True:
            return SupplyResult.DO_NOT_WANT_THIS_SUBMISSION
        return r2t.send_gif_img(what, url, ext, text)
    else:
        return SupplyResult.DO_NOT_WANT_THIS_SUBMISSION
