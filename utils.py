# encoding:utf-8

from urllib.parse import urlparse
import requests
import yaml
import os
import imghdr
import time

from imgurpython import ImgurClient


telegram_autoplay_limit = 10 * 1024 * 1024


def get_url(submission, mp4_instead_gif=True):
    '''
    return TYPE, URL, EXTENSION
    E.x.: return 'img', 'http://example.com/pic.png', 'png'
    '''
    _TYPE_IMG = 'img'
    _CONTENT_JPEG = 'image/jpeg'
    _CONTENT_PNG = 'image/png'
    _TYPE_GIF = 'gif'
    _CONTENT_GIF = 'image/gif'
    _CONTENT_MP4 = 'video/mp4'
    def what_is_inside(url):
        header = requests.head(url).headers
        if 'Content-Type' in header:
            return header['Content-Type']
        else:
            return ''

    url = submission.url
    url_content = what_is_inside(url)

    if (_CONTENT_JPEG == url_content or _CONTENT_PNG == url_content):
        return _TYPE_IMG, url, url_content.split('/')[1]

    if _CONTENT_GIF in url_content:
        if url.endswith('.gif') and mp4_instead_gif:
            # Let's try to find .mp4 file.
            url_mp4 = url[:-4] + '.mp4'
            if _CONTENT_MP4 == what_is_inside(url_mp4):
                return _TYPE_GIF, url_mp4, 'mp4'
        return _TYPE_GIF, url, 'gif'
    
    if url.endswith('.gifv'):
        if mp4_instead_gif:
            url_mp4 = url[:-5] + '.mp4'
            if _CONTENT_MP4 == what_is_inside(url_mp4):
                return _TYPE_GIF, url_mp4, 'mp4'
        if _CONTENT_GIF in what_is_inside(url[0:-1]):
            return _TYPE_GIF, url[0:-1], 'gif'

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
                what = _TYPE_IMG
                link = img['link']
                ext = img['type'].split('/')[1]
                if img['animated']:
                    what = _TYPE_GIF
                    link = img['mp4'] if mp4_instead_gif else img['gifv'][:-1]
                    ext = 'mp4' if mp4_instead_gif else 'gif'
                story[number] = {
                    'url': link,
                    'what': what,
                    'ext': ext
                }
            return 'album', story, None
        else:
            # Just imgur img
            img = imgur_client.get_image(path_parts[1].split('.')[0])
            if not img.animated:
                return _TYPE_IMG, img.link, img.type.split('/')[1]
            else:
                if mp4_instead_gif:
                    return _TYPE_GIF, img.mp4, 'mp4'
                else:
                    # return 'gif', img.link, 'gif'
                    return _TYPE_GIF, img.gifv[:-1], 'gif'
    else:
        return 'other', url, None


TEMP_FOLDER = '.'


class reddit2telegram_sender(object):
    '''
    docstring for reddit2telegram
    '''
    def __init__(self, t_channel, telepot_bot):
        super(reddit2telegram_sender, self).__init__()
        self.telepot_bot = telepot_bot
        self.t_channel = t_channel

    def _get_file_name(self, ext):
        return os.path.join(TEMP_FOLDER,
                            '{name}.{ext}'.format(name=self.t_channel[1:], ext=ext))

    def send_gif_img(self, what, url, ext, text):
        if what == 'gif':
            return self.send_gif(url, ext, text)
        elif what == 'img':
            return self.send_img(url, ext, text)
        else:
            return False

    def send_gif(self, url, ext, text):
        filename = self._get_file_name(ext)
        # Download gif
        if not download_file(url, filename):
            return False
        # Telegram will not autoplay big gifs
        if os.path.getsize(filename) > telegram_autoplay_limit:
            return False
        f = open(filename, 'rb')
        self.telepot_bot.sendDocument(self.t_channel, f, caption=text)
        f.close()
        return True

    def send_img(self, url, ext, text):
        filename = self._get_file_name(ext)
        # Download file
        if not download_file(url, filename):
            return False
        f = open(filename, 'rb')
        self.telepot_bot.sendPhoto(self.t_channel, f, caption=text)
        f.close()
        return True

    def send_text(self, text, disable_web_page_preview=False):
        self.telepot_bot.sendMessage(self.t_channel, text, disable_web_page_preview=disable_web_page_preview)
        return True


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


def just_send_an_album(story, r2t):
    def just_send(num, item):
        text = '# {}\n{}'.format(num, item['url'])
        r2t.send_text(text)

    for num, item in sorted(story.items(), key=lambda x: x[0]):
        text = '# {}'.format(num)
        if item['what'] == 'gif':
            if not r2t.send_gif(item['url'], item['ext'], text):
                just_send(num, item)
        elif item['what'] == 'img':
            if not r2t.send_img(item['url'], item['ext'], text):
                just_send(num, item)
        elif item['what'] == 'text':
            just_send(num, item)
        time.sleep(2)
