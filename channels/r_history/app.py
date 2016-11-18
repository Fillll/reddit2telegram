#encoding:utf-8

import os
import random
from urllib.parse import urlparse
import time

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
    channels = {'HistoryPorn': 0.5,
        'ArchivePorn': 0.01,
        # Add something from this list:
        # /r/ADifferentEra
        'BattlePaintings': 0.02,
        'BiographyFilms': 0.005,
        'Castles': 0.04,
        'Colorization': 0.1,
        'ColorizedHistory': 0.02,
        # /r/CombatFootage
        'FortPorn': 0.01,
        # /r/History
        # /r/HistoryNetwork
        'ImagesOfHistory': 0.005,
        'ImaginaryHistory': 0.005,
        'ImaginaryPolitics': 0.005,
        # /r/MapIt
        'MegalithPorn': 0.005,
        'OldIndia': 0.005,
        'OldSchoolCool': 0.15,
        'OldSchoolCreepy': 0.005,
        'Presidents': 0.005,
        'PropagandaPosters': 0.1,
        'RedditThroughHistory': 0.005,
        # /r/RestofHistoryPorn
        'TheWayWeWere': 0.01,
        'WarshipPorn': 0.02,
        'WWIIPics': 0.02,
        # /r/WWIIPlanes
        'ColdWarPosters': 0.005
    }
    return weighted_random(channels)


# subreddit = define_channel_for_today()
subreddit = 'HistoryPorn'
t_channel = '@RedditHistory'


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

    filename = 'r_history.{}'.format(ext)
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
        if len(text) > 200:
            text = link
            bot.sendMessage(t_channel, '{main_text}\n\n@RedditHistory'.format(main_text=title))
            time.sleep(2)
        f = open(filename, 'rb')
        bot.sendPhoto(t_channel, f, caption=text)
        f.close()
        return True
    else:
        return False
