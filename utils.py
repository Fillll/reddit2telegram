# encoding:utf-8

from urllib.parse import urlparse
import requests
import yaml
import os
import imghdr
import time

from imgurpython import ImgurClient


telegram_autoplay_limit = 10 * 1024 * 1024


def get_url(submission):
    def what_is_inside(url):
        header = requests.head(url).headers
        if 'Content-Type' in header:
            return header['Content-Type']
        else:
            return ''

    url = submission.url

    url_content = what_is_inside(url)
    if ('image/jpeg' == url_content or 'image/png' == url_content):
        return 'img', url, url_content.split('/')[1]

    if 'image/gif' in url_content:
        return 'gif', url, 'gif'
    
    if url.endswith('.gifv'):
        if 'image/gif' in what_is_inside(url[0:-1]):
            return 'gif', url[0:-1], 'gif'

    if submission.is_self is True:
        # Self submission with text
        return 'text', None, None

    if urlparse(url).netloc == 'imgur.com':
        # Imgur
        imgur_config = yaml.load(open('imgur.yml').read())
        imgur_client = ImgurClient(imgur_config['client_id'], imgur_config['client_secret'])
        path_parts = urlparse(url).path.split('/')
        if path_parts[1] == 'gallery':
            # TODO: gallary handling
            return 'other', url, None
        elif path_parts[1] == 'topic':
            # TODO: topic handling
            return 'other', url, None
        elif path_parts[1] == 'a':
            # An imgur album
            album = imgur_client.get_album(path_parts[2])
            story = {}
            for num, img in enumerate(album.images):
                number = num + 1
                story[number] = {
                    'link': img['link'],
                    'gif': img['animated'],
                    'type': img['type'].split('/')[1]
                }
            return 'album', story, None
        else:
            # Just imgur img
            img = imgur_client.get_image(path_parts[1].split('.')[0])
            if not img.animated:
                return 'img', img.link, img.type.split('/')[1]
            else:
                return 'gif', img.link, 'gif'
            

    else:
        return 'other', url, None


def download_file(url, filename):
    # http://stackoverflow.com/questions/16694907/how-to-download-large-file-in-python-with-requests-py
    # NOTE the stream=True parameter
    r = requests.get(url, stream=True)
    chunk_counter = 0
    with open(filename, 'wb') as f:
        for chunk in r.iter_content(chunk_size=1024):
            if chunk:  # filter out keep-alive new chunks
                f.write(chunk)
                #f.flush() commented by recommendation from J.F.Sebastian
                chunk_counter += 1
                # It is not possible to send greater than 50 MB via Telegram
                if chunk_counter > 50 * 1024:
                    return False
    return True


def just_send_an_album(t_channel, story, bot):
    def just_send(num, item, bot):
        text = '# {}\n{}'.format(num, item)
        bot.sendMessage(t_channel, text)

    for num, item in sorted(story.items(), key=lambda x: x[0]):
        filename = '{}.{}'.format(t_channel[1:], item['type'])
        if download_file(item['link'], filename):
            if item['gif'] is False:
                # Not animated, no gif.
                f = open(filename, 'rb')
                text = '# {}'.format(num)
                bot.sendPhoto(t_channel, f, caption=text)
                f.close()
            else:
                # Animated, gif
                if os.path.getsize(filename) <= telegram_autoplay_limit:
                    # It is small and it is gif
                    f = open(filename, 'rb')
                    text = '# {}'.format(num)
                    bot.sendDocument(t_channel, f, caption=text)
                    f.close()
                else:
                    # Not small or not gif
                    just_send(num, item['link'], bot)
        else:
            # Can not download
            just_send(num, item['link'], bot)
        time.sleep(2)
