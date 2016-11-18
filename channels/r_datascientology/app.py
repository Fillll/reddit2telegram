#encoding:utf-8

import random

from utils import get_url, just_send_an_album


def weighted_random(d):
    r = random.uniform(0, sum(val for val in d.values()))
    s = 0.0
    for k, w in d.items():
        s += w
        if r < s: return k
    return k


def define_channel_for_today():
    channels = {'dataisbeautiful': 8,
        'MapPorn': 5,
        'datasets': 1,
        'datascience': 2,
        'MachineLearning': 2,
        'visualization': 1,
        'Infographics': 2,
        'wordcloud': 0.7,
        'SampleSize': 0.7,
        'dataisugly': 1.2,
        'FunnyCharts': 0.6,
        'usdataisbeautiful': 0.2,
        'mathpics': 0.5,
        'statistics': 1,
        'pystats': 0.5,
        'opendata': 0.3,
        'bigdatajobs': 0.1,
        'bigdata': 0.2,
        'IPython': 0.1,
        'JupyterNotebooks': 0.1
    }
    return weighted_random(channels)


subreddit = define_channel_for_today()
t_channel = '@datascientology'


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
        base_url = submission.url
        text = '{}\n{}\n\n/r/{}\n{}'.format(title, base_url, subreddit, link)
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
