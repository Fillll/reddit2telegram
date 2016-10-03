#encoding:utf-8

import os
import imghdr
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
        'IPython': 0.05,
        'JupyterNotebooks': 0.05
    }
    return weighted_random(channels)


subreddit = define_channel_for_today()
t_channel = '@datascientology'


def just_send_message(submission, bot):
    title = submission.title
    link = submission.short_link
    if submission.is_self is True:    
        punchline = submission.selftext
        text = '{}\n\n{}\n\n/r/{}\n{}'.format(title, punchline, subreddit, link)
    else:
        url = submission.url
        text = '{}\n{}\n\n/r/{}\n{}'.format(title, url, subreddit, link)
    bot.sendMessage(t_channel, text)
    return True


def send_post(submission, bot):
    what, url = get_url(submission)
    title = submission.title
    link = submission.short_link
    if what == 'text':
        return just_send_message(submission, bot)
    else:
        text = '{}\n\n/r/{}\n{}'.format(title, subreddit, link)
        filename = 'r_data_related.file'
        if not download_file(url, filename):
            return just_send_message(submission, bot)
        new_filename = '{}.{}'.format(filename, imghdr.what(filename))
        os.rename(filename, new_filename)
        if what == 'gif':
            if os.path.getsize(new_filename) > telegram_autoplay_limit:
                return just_send_message(submission, bot)
            f = open(new_filename, 'rb')
            bot.sendDocument(t_channel, f, caption=text)
            f.close()
            return True
        elif what == 'other':
            if imghdr.what(new_filename) in ('jpeg', 'bmp', 'png'):
                f = open(new_filename, 'rb')
                bot.sendPhoto(t_channel, f, caption=text)
                f.close()
                return True
            else:
                text = '{}\n{}\n\n/r/{}\n{}'.format(title, url, subreddit, link)
                bot.sendMessage(t_channel, text)
                return True
        else:
            return False
