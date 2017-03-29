#encoding:utf-8

from utils import get_url


t_channel = '@reddit_all'
subreddit = 'all'


def send_post(submission, r2t):
    what, url, ext = get_url(submission)
    title = submission.title
    link = submission.shortlink
    sub = submission.subreddit
    text = '{}\n\n/r/{}\n{}'.format(title, sub, link)

    if what == 'text':
        punchline = submission.selftext
        text = '{}\n\n{}\n\n/r/{}\n{}'.format(title, punchline, sub, link)
        return r2t.send_text(text)
    elif what == 'other':
        base_url = submission.url
        text = '{}\n{}\n\n/r/{}\n{}'.format(title, base_url, sub, link)
        return r2t.send_text(text)
    elif what == 'album':
        base_url = submission.url
        text = '{}\n{}\n\n/r/{}\n{}'.format(title, base_url, sub, link)
        r2t.send_text(text)
        r2t.send_album(url)
        return True
    elif what in ('gif', 'img'):
        return r2t.send_gif_img(what, url, ext, text)
    else:
        return False
