#encoding:utf-8

import os
import random
from urllib.parse import urlparse

from utils import get_url, just_send_an_album


def weighted_random(d):
    r = random.uniform(0, sum(val for val in d.values()))
    s = 0.0
    for k, w in d.items():
        s += w
        if r < s: return k
    return k


def define_channel_for_today():
    channels = {'cats': 1,
        'StartledCats': 1,
        'CatsStandingUp': 1,
        'funny_cats': 1,
        'catpictures': 1,
        'CatSlaps': 1,
        'CatsAreAssholes': 1,
        'teefies': 1,
        'CatGifs': 1,
        'BigCatGifs': 1,
        'catreactiongifs': 1,
        'kittyhugs': 1,
        'kittyhugs': 1,
        'FunnyCatGifs': 1,
        'LazyCats': 1,
        'catsinboxes': 1,
        'CatHighFive': 1,
        'cathug': 1,
        'WigglyCats': 1,
        'catfreakouts': 1,
        'catremakesofmovies': 1
    }
    return weighted_random(channels)


subreddit = define_channel_for_today()
t_channel = '@RedditCats'


def send_post(submission, r2t):
    what, url, ext = get_url(submission)
    title = submission.title
    link = submission.short_link
    text = '{}\n{}'.format(title, link)
    domain = urlparse(url).netloc

    if what in ('text', 'other'):
        return False
    elif what == 'album':
        base_url = submission.url
        text = '{}\n{}\n\n{}'.format(title, base_url, link)
        r2t.send_text(text)
        just_send_an_album(url, r2t)
        return True
    elif what in ('gif', 'img'):
        return r2t.send_gif_img(what, url, ext, text)
    else:
        return False
