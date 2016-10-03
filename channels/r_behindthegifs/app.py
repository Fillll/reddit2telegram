#encoding:utf-8

import os
from urllib.parse import urlparse
import imghdr
import time

import yaml
from imgurpython import ImgurClient

from utils import get_url, download_file, telegram_autoplay_limit


subreddit = 'behindthegifs'
t_channel = '@r_behindthegifs'


def send_post(submission, bot):
    what, story = get_url(submission)
    if what != 'album':
        return False

    text = '{}\n{}\n\n{}'.format(submission.title, submission.url, submission.short_link)
    bot.sendMessage(t_channel, text)

    for num, item in sorted(story['behind'].items(), key=lambda x: x[0]):
        filename = 'r_behindthegifs.file'
        if download_file(item, filename):
            what_inside = imghdr.what(filename)
            if what_inside in ('jpeg', 'bmp', 'png'):
                new_filename = '{}.{}'.format(filename, what_inside)
                os.rename(filename, new_filename)
                f = open(new_filename, 'rb')
                text = '# {}'.format(num)
                bot.sendPhoto(t_channel, f, caption=text)
                f.close()
            else:
                text = '# {}\n{}'.format(num, item)
                bot.sendMessage(t_channel, text)
        else:
            text = '# {}\n{}'.format(num, item)
            bot.sendMessage(t_channel, text)
        time.sleep(2)

    for num, item in sorted(story['gifs'].items(), key=lambda x: x[0]):
        filename = 'r_behindthegifs.gif'
        if download_file(item, filename):
            what_inside = imghdr.what(filename)
            if what_inside == 'gif' and os.path.getsize(filename) <= telegram_autoplay_limit:
                f = open(filename, 'rb')
                text = '# {}'.format(num)
                bot.sendDocument(t_channel, f, caption=text)
                f.close()
            else:
                text = '# {}\n{}'.format(num, item)
                bot.sendMessage(t_channel, text)
        else:
            text = '# {}\n{}'.format(num, item)
            bot.sendMessage(t_channel, text)
        time.sleep(2)

    return True
