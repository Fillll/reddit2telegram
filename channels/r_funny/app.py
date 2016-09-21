#encoding:utf-8

import os
from utils import get_url, download_file
import imghdr


subreddit = 'funny'
t_channel = '@r_funny'


def send_post(submission, bot):
    what, url = get_url(submission)
    if what == 'text':
        title = submission.title
        punchline = submission.selftext
        link = submission.short_link
        text = '{}\n\n{}\n\n{}'.format(title, punchline, link)
        bot.sendMessage(t_channel, text)
        return True
    else:
        title = submission.title
        link = submission.short_link
        text = '{}\n{}'.format(title, link)
        filename = 'r_funny.file'
        if not download_file(url, filename):
            return False
        new_filename = '{}.{}'.format(filename, imghdr.what(filename))
        os.rename(filename, new_filename)
        if what == 'gif':
            if os.path.getsize(new_filename) > 10 * 1024 * 1024:
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
                text = '{}\n{}\n\n{}'.format(title, url, link)
                bot.sendMessage(t_channel, text)
                return True
        else:
            return False
