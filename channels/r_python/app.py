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
    channels = {
        'flask': 3,
        'Python': 8,
        'django': 1,
        'MachineLearning': 2,
        'lua': 5,
        'djangolearning': 4
    }
    return weighted_random(channels)


subreddit = define_channel_for_today()
t_channel = '@pythondaily'


def send_post(submission, bot):
    what, url = get_url(submission)
    title = submission.title
    link = submission.short_link
    if what == 'text':
        punchline = submission.selftext
        text = '{}\n\n{}\n\n/r/{}\n{}'.format(title, punchline, subreddit, link)
        bot.sendMessage(t_channel, text)
        return True
    else:
        text = '{}\n\n/r/{}\n{}'.format(title, subreddit, link)
        filename = 'r_data_related.file'
        if not download_file(url, filename):
            return False
        new_filename = '{}.{}'.format(filename, imghdr.what(filename))
        os.rename(filename, new_filename)
        if what == 'gif':
            if os.path.getsize(new_filename) > telegram_autoplay_limit:
                return False
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
