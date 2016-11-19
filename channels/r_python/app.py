#encoding:utf-8

import random

from utils import get_url, download_file, telegram_autoplay_limit


def weighted_random(d):
    r = random.uniform(0, sum(val for val in d.values()))
    s = 0.0
    for k, w in d.items():
        s += w
        if r < s: return k
    return k


def define_channel_for_today():
    channels = {
        'flask': 3,
        'Python': 6,
        'django': 4,
        'MachineLearning': 1,
        'djangolearning': 1,
        'IPython': 5,
        'pystats': 4,
        'JupyterNotebooks': 3
    }
    return weighted_random(channels)


subreddit = define_channel_for_today()
t_channel = '@pythondaily'


def send_post(submission, r2t):
    what, url, ext = get_url(submission)
    title = submission.title
    link = submission.short_link
    text = '{}\n\n/r/{}\n{}'.format(title, subreddit, link)

    if what == 'text':
        punchline = submission.selftext
        text = '{}\n\n{}\n\n/r/{}\n{}'.format(title, punchline, subreddit, link)
        return r2t.send_text(text)
    elif what == 'other':
        url = submission.url
        text = '{}\n{}\n\n/r/{}\n{}'.format(title, url, subreddit, link)
        return r2t.send_text(text)
    elif what == 'album':
        base_url = submission.url
        text = '{}\n{}\n\n/r/{}\n{}'.format(title, base_url, subreddit, link)
        r2t.send_text(text)
        just_send_an_album(url, r2t)
        return True
    elif what in ('gif', 'img'):
        return r2t.send_gif_img(what, url, ext, text)
    else:
        return False
