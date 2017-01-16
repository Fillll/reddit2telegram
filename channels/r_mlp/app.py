#encoding:utf-8

from urllib.parse import urlparse

from utils import get_url


t_channel = '@r_mlp'
subreddit = 'mylittlepony'


def send_post(submission, r2t):
    what, url, ext = get_url(submission)
    title = submission.title
    link = submission.shortlink
    text = '{}\n{}'.format(title, link)

    if what == 'text':
        return False
    elif what == 'album':
        base_url = submission.url
        text = '{}\n{}\n\n{}'.format(title, base_url, link)
        r2t.send_text(text)
        r2t.send_album(url)
        return True
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
