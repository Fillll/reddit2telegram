#encoding:utf-8

import os
import random

from utils import get_url, download_file


subreddit = 'pics'
t_channel = '@r_pics_redux'


def send_post(submission, bot):
    what, url, ext = get_url(submission)
    title = submission.title
    link = submission.short_link
    text = '{}\n{}'.format(title, link)

    if what not in ('img'):
        return False
    # elif what == 'album':
    #     just_send_an_album(t_channel, url, bot)
    #     return True

    filename = 'r_pics.{}'.format(ext)
    if not download_file(url, filename):
        return False

    f = open(filename, 'rb')
    bot.sendPhoto(t_channel, f, caption=text)
    f.close()
    return True
