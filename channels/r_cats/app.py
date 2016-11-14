#encoding:utf-8

import os
import random
from urllib.parse import urlparse

from utils import (get_url, download_file, telegram_autoplay_limit,
                   just_send_an_album)


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
        'BigCatGifs': 1
    }
    return weighted_random(channels)


subreddit = define_channel_for_today()
t_channel = '@RedditCats'


def just_send_message(submission, bot):
    title = submission.title
    link = submission.short_link
    if submission.is_self is True:    
        punchline = submission.selftext
        text = '{}\n\n{}\n\n{}'.format(title, punchline, link)
    else:
        url = submission.url
        text = '{}\n{}\n\n{}'.format(title, url, link)
    bot.sendMessage(t_channel, text)
    return True


def send_post(submission, bot):
    what, url, ext = get_url(submission)
    title = submission.title
    link = submission.short_link
    text = '{}\n{}'.format(title, link)
    domain = urlparse(url).netloc

    if what == 'text':
        return False
    elif what == 'album':
        just_send_message(submission, bot)
        just_send_an_album(t_channel, url, bot)
        return True
    elif what == 'other':
        if domain in ('www.youtube.com', 'youtu.be'):
            text = '{}\n{}\n\n{}'.format(title, url, link)
            bot.sendMessage(t_channel, text)
            return True
        else:
            return False

    filename = 'r_cats.{}'.format(ext)
    if not download_file(url, filename):
        return False
    if os.path.getsize(filename) > telegram_autoplay_limit:
        return False

    if what == 'gif':
        f = open(filename, 'rb')
        bot.sendDocument(t_channel, f, caption=text)
        f.close()
        return True
    elif what == 'img':
        f = open(filename, 'rb')
        bot.sendPhoto(t_channel, f, caption=text)
        f.close()
        return True
    else:
        return False
