#encoding:utf-8

import os

from utils import get_url, download_file


subreddit = 'gifs'
t_channel = '@r_gifs'


def send_post(submission, bot):
    what, gif_url = get_url(submission)
    if what != "gif":
        return False
    # Download gif
    download_file(gif_url)
    # Telegram will not autoplay big gifs
    if os.path.getsize('r_gifs.gif') > 10 * 1024 * 1024:
        return False
    title = submission.title
    link = submission.short_link
    text = '%s\n%s\n\nby @r_gifs' % (title, link)
    f = open('r_gifs.gif', 'rb')
    bot.sendDocument(t_channel, f, caption=text)
    f.close()
    return True
