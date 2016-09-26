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
        gifurl = 'https://thumbs.gfycat.com' + urlparse(url).path + '-size_restricted.gif'
        return 'gif', gifurl
    elif urlparse(url).netloc == 'streamable.com':
        mp4Url = 'https://cdn.streamable.com/video/mp4' + urlparse(url).path + '.mp4'
        return 'mp4', mp4Url
    else:
        return 'other', url

def send_post(submission, bot):
    what, gif_url = get_gif(submission)
    if what not in ('gif', 'mp4'):
        return False
    # Determine file
    if what == 'gif':
        t_file = 'asiangirlsbeingcute.gif'
    elif what == 'mp4':
        t_file = 'asiangirlsbeingcute.mp4'
    #Download file    
    if not download_file(gif_url, t_file):
        return False
    # Telegram will not autoplay big gifs
    if os.path.getsize(t_file) > telegram_autoplay_limit:
        return False
    title = submission.title
    link = submission.short_link
    text = '%s\n%s' % (title, link)
    f = open(t_file, 'rb')
    bot.sendDocument(t_channel, f, caption=text)
    f.close()
    return True
