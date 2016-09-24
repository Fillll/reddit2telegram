#encoding:utf-8

import os

from utils import download_file, telegram_autoplay_limit
from urllib.parse import urlparse

subreddit = 'asiangirlsbeingcute'
t_channel = '@asiangirlsbeingcute'

def get_gif(submission):
    url = submission.url
    # TODO: Better url validation
    if url.endswith('.gif'):
        return 'gif', url
    elif url.endswith('.gifv'):
        return 'gif', url[0:-1]
    elif urlparse(url).netloc == 'www.reddit.com':
        return 'text', None
    elif urlparse(url).netloc == 'gfycat.com':
        gifurl = 'https://thumbs.gfycat.com' + urlparse(url).path + '-small.gif'
        return 'gif', gifurl
    else:
        return 'other', url

def send_post(submission, bot):
    what, gif_url = get_gif(submission)
    if what != 'gif':
        return False
    # Download gif
    if not download_file(gif_url, 'asiangirlsbeingcute.gif'):
        return False
    # Telegram will not autoplay big gifs
    if os.path.getsize('asiangirlsbeingcute.gif') > telegram_autoplay_limit:
        return False
    title = submission.title
    link = submission.short_link
    text = '%s\n%s\n\nby @asiangirlsbeingcute' % (title, link)
    f = open('asiangirlsbeingcute.gif', 'rb')
    bot.sendDocument(t_channel, f, caption=text)
    f.close()
    return True
