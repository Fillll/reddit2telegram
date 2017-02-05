# encoding:utf-8

from urllib.parse import urlparse
import requests
import os
import imghdr
import time
import random
import re
import hashlib
from datetime import datetime

from imgurpython import ImgurClient
import yaml
import pymongo
import telepot


TELEGRAM_AUTOPLAY_LIMIT = 10 * 1024 * 1024


TYPE_IMG = 'img'
CONTENT_JPEG = 'image/jpeg'
CONTENT_PNG = 'image/png'
TYPE_GIF = 'gif'
CONTENT_GIF = 'image/gif'
CONTENT_MP4 = 'video/mp4'


TEMP_FOLDER = 'tmp'


def get_url(submission, mp4_instead_gif=True):
    '''
    return TYPE, URL, EXTENSION
    E.x.: return 'img', 'http://example.com/pic.png', 'png'
    '''
    
    def what_is_inside(url):
        header = requests.head(url).headers
        if 'Content-Type' in header:
            return header['Content-Type']
        else:
            return ''

    url = submission.url
    url_content = what_is_inside(url)

    if (CONTENT_JPEG == url_content or CONTENT_PNG == url_content):
        return TYPE_IMG, url, url_content.split('/')[1]

    if CONTENT_GIF in url_content:
        if url.endswith('.gif') and mp4_instead_gif:
            # Let's try to find .mp4 file.
            url_mp4 = url[:-4] + '.mp4'
            if CONTENT_MP4 == what_is_inside(url_mp4):
                return TYPE_GIF, url_mp4, 'mp4'
        return TYPE_GIF, url, 'gif'
    
    if url.endswith('.gifv'):
        if mp4_instead_gif:
            url_mp4 = url[:-5] + '.mp4'
            if CONTENT_MP4 == what_is_inside(url_mp4):
                return TYPE_GIF, url_mp4, 'mp4'
        if CONTENT_GIF in what_is_inside(url[0:-1]):
            return TYPE_GIF, url[0:-1], 'gif'

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
                what = TYPE_IMG
                link = img['link']
                ext = img['type'].split('/')[1]
                if img['animated']:
                    what = TYPE_GIF
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
                return TYPE_IMG, img.link, img.type.split('/')[1]
            else:
                if mp4_instead_gif:
                    return TYPE_GIF, img.mp4, 'mp4'
                else:
                    # return 'gif', img.link, 'gif'
                    return TYPE_GIF, img.gifv[:-1], 'gif'
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


def md5_sum_from_url(url):
    r = requests.get(url, stream=True)
    chunk_counter = 0
    hash_store = hashlib.md5()
    for chunk in r.iter_content(chunk_size=1024):
        if chunk:  # filter out keep-alive new chunks
            hash_store.update(chunk)
            chunk_counter += 1
            # It is not possible to send greater than 50 MB via Telegram
            if chunk_counter > 50 * 1024:
                return None
    return hash_store.hexdigest()


# def md5_sum_from_file(filename):
#     # http://stackoverflow.com/questions/7829499/using-hashlib-to-compute-md5-digest-of-a-file-in-python-3
#     with open(filename, mode='rb') as f:
#         d = hashlib.md5()
#         for buf in iter(partial(f.read, 1024), b''):
#             d.update(buf)
#     return d.hexdigest()


def weighted_random_subreddit(d):
    r = random.uniform(0, sum(val for val in d.values()))
    s = 0.0
    for k, w in d.items():
        s += w
        if r < s: return k
    return k


class Reddit2TelegramSender(object):
    '''
    docstring for reddit2telegram
    '''
    def __init__(self, t_channel, config):
        super(Reddit2TelegramSender, self).__init__()
        self.config = config
        self.telepot_bot = telepot.Bot(self.config['telegram_token'])
        self.t_channel = t_channel
        self._make_mongo_connections()
        self._store_stats()

    def _make_mongo_connections(self):
        self.stats = pymongo.MongoClient(host=self.config['db_host'])[self.config['db']]['stats']
        self.urls = pymongo.MongoClient(host=self.config['db_host'])[self.config['db']]['urls']
        self.contents = pymongo.MongoClient(host=self.config['db_host'])[self.config['db']]['contents']

    def _store_stats(self):
        self.stats.insert_one({
            'channel': self.t_channel.lower(),
            'ts': datetime.utcnow(),
            'members_cnt': self.telepot_bot.getChatMembersCount(self.t_channel)
        })

    def _get_file_name(self, ext):
        return os.path.join(TEMP_FOLDER,
                            '{name}.{ext}'.format(name=self.t_channel[1:], ext=ext))

    def _split_200(self, text):
        new_text = ''
        next_text = ''
        list_of_words = re.split('[ \n]', text)
        switched = False
        for i in list_of_words:
            if (len(new_text) + len(i) + 1 < 196) and not switched:
                new_text += i + ' '
            else:
                switched = True
                next_text += ' ' + i
        return new_text + ' ...', '... ' + next_text

    def _split_4096(self, text):
        new_text = text[:4096]
        next_text = text[4096:]
        return new_text, next_text

    def was_before(self, url):
        result = self.urls.find_one({
            'channel': self.t_channel.lower(),
            'url': {'$regex': url.split('/')[-1]}
        })
        if result is None:
            return False
        else:
            return True

    def mark_as_was_before(self, url):
        self.urls.insert_one({
            'url': url,
            'ts': datetime.utcnow(),
            'channel': self.t_channel.lower()
        })

    def dup_check_and_mark(self, url):
        md5_sum = md5_sum_from_url(url)
        if md5_sum is None:
            return False
        result = self.contents.find_one({
            'channel': self.t_channel.lower(),
            'md5_sum': md5_sum
        })
        if result is None:
            self.contents.insert_one({
                'md5_sum': md5_sum,
                'ts': datetime.utcnow(),
                'channel': self.t_channel.lower()
            })
            return False
        else:
            return True

    # def dup_content(self, url):
    #     md5_sum = md5_sum_from_url(url)
    #     if md5_sum is None:
    #         return None
    #     result = self.contents.find_one({
    #         'channel': self.t_channel.lower(),
    #         'md5_sum': md5_sum
    #     })
    #     if result is None:
    #         return False
    #     else:
    #         return True

    # def mark_as_dup_content_url(self, url):
    #     md5_sum = md5_sum_from_url(url)
    #     if md5_sum is None:
    #         return
    #     self.contents.insert_one({
    #         'md5_sum': md5_sum,
    #         'ts': datetime.utcnow(),
    #         'channel': self.t_channel.lower()
    #     })

    # def mark_as_dup_content_file(self, content_filename):
    #     md5_sum = md5_sum_from_file(content_filename)
    #     self.contents.insert_one({
    #         'md5_sum': md5_sum,
    #         'ts': datetime.utcnow(),
    #         'channel': self.t_channel.lower()
    #     })

    def send_gif_img(self, what, url, ext, text):
        if what == TYPE_GIF:
            return self.send_gif(url, ext, text)
        elif what == TYPE_IMG:
            return self.send_img(url, ext, text)
        else:
            return False

    def send_gif(self, url, ext, text):
        filename = self._get_file_name(ext)
        # Download gif
        if not download_file(url, filename):
            return False
        # Telegram will not autoplay big gifs
        if os.path.getsize(filename) > TELEGRAM_AUTOPLAY_LIMIT:
            return False
        next_text = ''
        if len(text) > 200:
            text, next_text = self._split_200(text)
        f = open(filename, 'rb')
        self.telepot_bot.sendDocument(self.t_channel, f, caption=text)
        f.close()
        if len(next_text) > 1:
            time.sleep(2)
            self.send_text(next_text, disable_web_page_preview=True)
        return True

    def send_img(self, url, ext, text):
        filename = self._get_file_name(ext)
        # Download file
        if not download_file(url, filename):
            return False
        next_text = ''
        if len(text) > 200:
            text, next_text = self._split_200(text)
        f = open(filename, 'rb')
        self.telepot_bot.sendPhoto(self.t_channel, f, caption=text)
        f.close()
        if len(next_text) > 1:
            time.sleep(2)
            self.send_text(next_text, disable_web_page_preview=True)
        return True

    def send_text(self, text, disable_web_page_preview=False):
        if len(text) < 4096:
            self.telepot_bot.sendMessage(self.t_channel, text, disable_web_page_preview=disable_web_page_preview)
            return True
        # If text is longer than 4096 symnols.
        next_text = text
        while len(next_text) > 0:
            new_text, next_text = self._split_4096(next_text)
            self.telepot_bot.sendMessage(self.t_channel, new_text, disable_web_page_preview=disable_web_page_preview)
            time.sleep(2)
        return True

    def send_album(self, story):
        def just_send(num, item):
            text = '# {}\n{}'.format(num, item['url'])
            self.send_text(text)

        for num, item in sorted(story.items(), key=lambda x: x[0]):
            text = '# {}'.format(num)
            if item['what'] == TYPE_GIF:
                if not self.send_gif(item['url'], item['ext'], text):
                    just_send(num, item)
            elif item['what'] == TYPE_IMG:
                if not self.send_img(item['url'], item['ext'], text):
                    just_send(num, item)
            elif item['what'] == 'text':
                just_send(num, item)
            time.sleep(2)
        return True
