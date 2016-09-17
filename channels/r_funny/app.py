#encoding:utf-8

import os
from urllib.parse import urlparse

import requests


subreddit = 'funny'
t_channel = '@r_funny'


def get_url(submission):
    url = submission.url
    # TODO: Better url validation
    if url.endswith('.gif'):
        return 'gif', url
    elif url.endswith('.gifv'):
        return 'gif', url[0:-1]
    elif url.endswith('.jpg'):
        return 'pic', url
    elif urlparse(url).netloc == 'www.reddit.com':
        return 'text', None
    else:
        return None, None


def download_file(url, filename):
    # http://stackoverflow.com/questions/16694907/how-to-download-large-file-in-python-with-requests-py
    # NOTE the stream=True parameter
    r = requests.get(url, stream=True)
    with open(filename, 'wb') as f:
        for chunk in r.iter_content(chunk_size=1024): 
            if chunk:  # filter out keep-alive new chunks
                f.write(chunk)
                #f.flush() commented by recommendation from J.F.Sebastian
    return True


def send_post(submission, bot):
    what, url = get_url(submission)
    if what == 'text':
        title = submission.title
        punchline = submission.selftext
        link = submission.short_link
        text = '{}\n\n{}\n\n{}'.format(title, punchline, link)
        bot.sendMessage(t_channel, text)
        return True
    elif what == 'gif':
        filename = 'r_funny.gif'
        download_file(url, filename)
        if os.path.getsize(filename) > 10 * 1024 * 1024:
            return False
        title = submission.title
        link = submission.short_link
        text = '%s\n%s' % (title, link)
        f = open(filename, 'rb')
        bot.sendDocument(t_channel, f, caption=text)
        f.close()
        return True
    elif what == 'pic':
        filename = 'r_funny.jpg'
        download_file(url, filename)
        if os.path.getsize(filename) > 10 * 1024 * 1024:
            return False
        title = submission.title
        link = submission.short_link
        text = '%s\n%s' % (title, link)
        f = open(filename, 'rb')
        bot.sendPhoto(t_channel, f, caption=text)
        f.close()
        return True
    else:
        return False
