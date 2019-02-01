#encoding:utf-8
from urllib.parse import urlparse

from utils import get_url, weighted_random_subreddit
from utils import SupplyResult


t_channel = '@dash_cams'
subreddit = weighted_random_subreddit({
    'Roadcam': 1.00,
})


def send_post(submission, r2t):
    what, url, ext = get_url(submission)
    title = submission.title
    link = submission.shortlink
    text = '{}\n{}'.format(title, link)

    if what == 'text':
        return SupplyResult.DO_NOT_WANT_THIS_SUBMISSION
    elif what == 'album':
        return SupplyResult.DO_NOT_WANT_THIS_SUBMISSION
    elif what == 'other':
        domain = urlparse(url).netloc
        if domain in ('www.youtube.com', 'youtu.be'):
            text = '{}\n{}\n\n{}'.format(title, url, link)
            return r2t.send_text(text)
        else:
            return SupplyResult.DO_NOT_WANT_THIS_SUBMISSION
    elif what in ('gif', 'img'):
        return r2t.send_gif_img(what, url, ext, text)
    else:
        return SupplyResult.DO_NOT_WANT_THIS_SUBMISSION
