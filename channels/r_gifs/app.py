#encoding:utf-8

import os

from utils import get_url, download_file, telegram_autoplay_limit


subreddit = 'gifs'
t_channel = '@r_gifs'


def send_post(submission, bot):
    what, gif_url, _ = get_url(submission)
    if what != 'gif':
        return False

    title = submission.title
    link = submission.short_link

    if submission.over_18:
        url = submission.url
        text = 'NSFW\n{}\n{}\n\n{}\n\nby @r_gifs'.format(url, title, link)
        bot.sendMessage(t_channel, text, disable_web_page_preview=True)
        return True

    # Download gif
    if not download_file(gif_url, 'r_gifs.gif'):
        return False
    # Telegram will not autoplay big gifs
    if os.path.getsize('r_gifs.gif') > telegram_autoplay_limit:
        return False
    text = '{}\n{}\n\nby @r_gifs'.format(title, link)
    f = open('r_gifs.gif', 'rb')
    bot.sendDocument(t_channel, f, caption=text)
    f.close()
    return True
