#encoding:utf-8

import os

from utils import get_url, download_file, telegram_autoplay_limit, just_send_an_album


subreddit = 'funny'
t_channel = '@r_funny'


def send_post(submission, bot):
    what, url, ext = get_url(submission)
    title = submission.title
    link = submission.short_link

    if what == 'text':
        punchline = submission.selftext        
        text = '{}\n\n{}\n\n{}'.format(title, punchline, link)
        bot.sendMessage(t_channel, text)
        return True
    elif what == 'album':
        text = '{}\n{}\n\n{}'.format(title, submission.url, link)
        bot.sendMessage(t_channel, text)
        just_send_an_album(t_channel, url, bot)
        return True

    filename = 'r_funny.{}'.format(ext)
    if not download_file(url, filename):
        return False
    if os.path.getsize(filename) > telegram_autoplay_limit:
        return False
    text = '{}\n{}'.format(title, link)

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
