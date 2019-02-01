#encoding:utf-8

from urllib.parse import urlparse

from utils import get_url, weighted_random_subreddit
from utils import SupplyResult


t_channel = '@RedditHistory'
subreddit = weighted_random_subreddit({
    'HistoryPorn': 0.5,
    'ArchivePorn': 0.01,
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
