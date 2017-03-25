#encoding:utf-8

from urllib.parse import urlparse

from utils import get_url, weighted_random_subreddit


t_channel = '@denpasong'
subreddit = weighted_random_subreddit({
    'denpa': 0.5,
    'denpasong': 0.5,
})


def send_post(submission, r2t):
    what, url, ext = get_url(submission)
    title = submission.title
    link = submission.shortlink
    text = '{}\n{}'.format(title, link)

    if what == 'text':
        return False
    elif what == 'album':
        return False
    elif what == 'other':
        domain = urlparse(url).netloc
        if domain in ('www.youtube.com', 'youtu.be'):
            text = '{}\n{}\n\n{}'.format(title, url, link)
            return r2t.send_text(text)
        else:
            return False
    elif what in ('gif', 'img'):
        return r2t.send_gif_img(what, url, ext, text)
    else:
        return False
