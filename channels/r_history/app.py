#encoding:utf-8

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


subreddit = define_channel_for_today()
t_channel = '@RedditHistory'


def send_post(submission, r2t):
    what, url, ext = get_url(submission)
    title = submission.title
    link = submission.short_link
    text = '{}\n{}'.format(title, link)
    domain = urlparse(url).netloc

    if what == 'text':
        return False
    elif what == 'album':
        # just_send_message(submission, bot)
        # just_send_an_album(t_channel, url, bot)
        # return True
        return False
    elif what == 'other':
        if domain in ('www.youtube.com', 'youtu.be'):
            text = '{}\n{}\n\n{}'.format(title, url, link)
            return r2t.send_text(text)
        else:
            return False

    if what == 'gif':
        return r2t.send_gif(url, ext, text)
    elif what == 'img':
        return r2t.send_img(url, ext, text)
        # if len(text) > 200:
        #     text = link
        #     bot.sendMessage(t_channel, '{main_text}\n\n@RedditHistory'.format(main_text=title))
        #     time.sleep(2)
        # f = open(filename, 'rb')
        # bot.sendPhoto(t_channel, f, caption=text)
        # f.close()
        # return True
    else:
        return False
