#encoding:utf-8

from utils import get_url, weighted_random_subreddit
from utils import SupplyResult


subreddit = 'wheredidthesodago'
t_channel = '@r_wheredidthesodago'
footer = 'by {}'.format(t_channel)


def send_post(submission, r2t):
    what, url, ext = get_url(submission)
    title = submission.title
    link = submission.shortlink
    text = '{}\n{}\n\n{}'.format(title, link, footer)
    if what == 'gif':
        if r2t.dup_check_and_mark(url) is True:
            return SupplyResult.DO_NOT_WANT_THIS_SUBMISSION
        return r2t.send_gif_img(what, url, ext, text)
    else:
        return SupplyResult.DO_NOT_WANT_THIS_SUBMISSION
