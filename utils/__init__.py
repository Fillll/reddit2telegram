# encoding:utf-8

from urllib.parse import urlparse
import requests
from requests.exceptions import InvalidSchema, MissingSchema
import os
import imghdr
import time
import random
import re
import hashlib
from datetime import datetime
import logging
import enum

from imgurpython import ImgurClient
import yaml
import pymongo
from pymongo.collection import ReturnDocument
import telepot
from gfycat.client import GfycatClient
from telepot.exception import TelegramError


TELEGRAM_AUTOPLAY_LIMIT = 10 * 1024 * 1024
TELEGRAM_VIDEO_LIMIT = 50 * 1024 * 1024


ALBUM_LIMIT = 20


TYPE_IMG = 'img'
CONTENT_JPEG = 'image/jpeg'
CONTENT_PNG = 'image/png'

TYPE_GIF = 'gif'
CONTENT_GIF = 'image/gif'
CONTENT_MP4 = 'video/mp4'

TYPE_TEXT = 'text'
TYPE_OTHER = 'other'
TYPE_ALBUM = 'album'
TYPE_VIDEO = 'video'


TEMP_FOLDER = 'tmp'


ERRORS_CNT_LIMIT = 5


@enum.unique
class SupplyResult(enum.Enum):
    SUCCESSFULLY = 0
    DO_NOT_WANT_THIS_SUBMISSION = 1
    SKIP_FOR_NOW = 2
    STOP_THIS_SUPPLY = 3


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

    if submission.is_video:
        if 'reddit_video' in submission.media:
            return TYPE_GIF, submission.media['reddit_video']['fallback_url'], 'mp4'
            # return TYPE_VIDEO, submission.media['reddit_video']['fallback_url'], None
            # return TYPE_OTHER, url, None

    try:
        if len(submission.crosspost_parent_list) > 0:
            parent_submission_json = submission.crosspost_parent_list[0]
            if parent_submission_json['is_video'] == True:
                if 'reddit_video' in parent_submission_json['media']:
                    return TYPE_GIF, parent_submission_json['media']['reddit_video']['fallback_url'], 'mp4'
    except:
        # Not a crosspost
        pass

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
        return TYPE_TEXT, None, None

    if urlparse(url).netloc == 'imgur.com':
        # Imgur
        imgur_config = yaml.load(open(os.path.join('configs', 'imgur.yml')).read())
        imgur_client = ImgurClient(imgur_config['client_id'], imgur_config['client_secret'])
        path_parts = urlparse(url).path.split('/')
        if path_parts[1] == 'gallery':
            # TODO: gallary handling
            return TYPE_OTHER, url, None
        elif path_parts[1] == 'topic':
            # TODO: topic handling
            return TYPE_OTHER, url, None
        elif path_parts[1] == 'a':
            # An imgur album
            album = imgur_client.get_album(path_parts[2])
            story = dict()
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
            if len(story) == 1:
                return story[1]['what'], story[1]['url'], story[1]['ext']
            return TYPE_ALBUM, story, None
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
    elif 'gfycat.com' in urlparse(url).netloc:
        client = GfycatClient()
        rname = re.findall(r'gfycat.com\/(?:detail\/)?(\w*)', url)[0]
        try:
            urls = client.query_gfy(rname)['gfyItem']
            if mp4_instead_gif:
                return TYPE_GIF, urls['mp4Url'], 'mp4'
            else:
                return TYPE_GIF, urls['max5mbGif'], 'gif'
        except KeyError:
            logging.info('Gfy fail prevented!')
            return TYPE_OTHER, url, None
    else:
        return TYPE_OTHER, url, None


def download_file(url, filename):
    # http://stackoverflow.com/questions/16694907/how-to-download-large-file-in-python-with-requests-py
    # NOTE the stream=True parameter
    r = requests.get(url, stream=True)
    chunk_counter = 0
    chunk_size = 1024
    with open(filename, 'wb') as f:
        for chunk in r.iter_content(chunk_size=chunk_size):
            if chunk:  # filter out keep-alive new chunks
                f.write(chunk)
                #f.flush() commented by recommendation from J.F.Sebastian
                chunk_counter += 1
                # It is not possible to send greater than 50 MB via Telegram
                if chunk_counter > TELEGRAM_VIDEO_LIMIT / chunk_size:
                    return False
    return True


def md5_sum_from_url(url):
    try:
        r = requests.get(url, stream=True)
    except InvalidSchema:
        return None
    except MissingSchema:
        return None
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


def weighted_random_subreddit(weights):
    random_value = random.uniform(0, sum(val for val in weights.values()))
    cumulative_sum = 0.0
    for k, w in weights.items():
        cumulative_sum += w
        if random_value < cumulative_sum:
            return k
    return k


class Reddit2TelegramSender(object):
    '''
    docstring for reddit2telegram
    '''
    def __init__(self, t_channel, config):
        super(Reddit2TelegramSender, self).__init__()
        self.config = config
        self.telepot_bot = telepot.Bot(self.config['telegram']['token'])
        self.t_channel = t_channel
        self._make_mongo_connections()
        time.sleep(2)

    def _make_mongo_connections(self):
        self.stats = pymongo.MongoClient(host=self.config['db']['host'])[self.config['db']['name']]['stats']
        self.stats.ensure_index([('channel', pymongo.ASCENDING), ('ts', pymongo.ASCENDING)])
        self.urls = pymongo.MongoClient(host=self.config['db']['host'])[self.config['db']['name']]['urls']
        self.urls.ensure_index([('channel', pymongo.ASCENDING), ('url', pymongo.ASCENDING)])
        self.contents = pymongo.MongoClient(host=self.config['db']['host'])[self.config['db']['name']]['contents']
        self.contents.ensure_index([('channel', pymongo.ASCENDING), ('md5_sum', pymongo.ASCENDING)])
        self.errors = pymongo.MongoClient(host=self.config['db']['host'])[self.config['db']['name']]['errors']
        self.errors.ensure_index([('channel', pymongo.ASCENDING), ('url', pymongo.ASCENDING)])

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

    def store_error_link(self, channel, url):
        return self.errors.find_one_and_update(
            {
                'channel': channel.lower(),
                'url': url.lower()
            },
            {
                '$inc': {'cnt': 1},
                '$set': {'ts': datetime.utcnow()}
            },
            projection={'cnt': True, '_id': False},
            return_document=ReturnDocument.AFTER,
            upsert=True
        )

    def too_much_errors(self, url):
        result = self.errors.find_one({
            'channel': self.t_channel.lower(),
            'url': url.lower()
        })
        if result is None:
            return False
        elif result['cnt'] >= ERRORS_CNT_LIMIT:
            return True
        else:
            return False

    def was_before(self, url):
        result = self.urls.find_one({
            'channel': self.t_channel.lower(),
            'url': {'$regex': url.split('/')[-1]}
        })
        if result is None:
            return False
        else:
            return True

    def mark_as_was_before(self, url, sent=True):
        self.urls.insert_one({
            'url': url,
            'ts': datetime.utcnow(),
            'channel': self.t_channel.lower(),
            'sent': sent
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
            logging.info('Duplicated found!')
            return True

    def send_gif_img(self, what, url, ext, text, parse_mode=None):
        if what == TYPE_GIF:
            return self.send_gif(url, ext, text, parse_mode)
        elif what == TYPE_IMG:
            return self.send_img(url, ext, text, parse_mode)
        else:
            return SupplyResult.DO_NOT_WANT_THIS_SUBMISSION

    def send_gif(self, url, ext, text, parse_mode=None):
        filename = self._get_file_name(ext)
        # Download gif
        if not download_file(url, filename):
            return SupplyResult.DO_NOT_WANT_THIS_SUBMISSION
        # Telegram will not autoplay big gifs
        if os.path.getsize(filename) > TELEGRAM_AUTOPLAY_LIMIT:
            return SupplyResult.DO_NOT_WANT_THIS_SUBMISSION
        next_text = ''
        if len(text) > 200:
            text, next_text = self._split_200(text)
        f = open(filename, 'rb')
        self.telepot_bot.sendDocument(self.t_channel, f, caption=text, parse_mode=parse_mode)
        f.close()
        if len(next_text) > 1:
            time.sleep(2)
            self.send_text(next_text, disable_web_page_preview=True, parse_mode=parse_mode)
        return SupplyResult.SUCCESSFULLY

    def send_video(self, url, text, parse_mode=None):
        filename = self._get_file_name('ext')
        # Download gif
        if not download_file(url, filename):
            return SupplyResult.DO_NOT_WANT_THIS_SUBMISSION
        # Telegram will not autoplay big gifs
        if os.path.getsize(filename) > TELEGRAM_VIDEO_LIMIT:
            return SupplyResult.DO_NOT_WANT_THIS_SUBMISSION
        next_text = ''
        if len(text) > 200:
            text, next_text = self._split_200(text)
        f = open(filename, 'rb')
        self.telepot_bot.sendVideo(self.t_channel, f, caption=text, parse_mode=parse_mode)
        f.close()
        if len(next_text) > 1:
            time.sleep(2)
            self.send_text(next_text, disable_web_page_preview=True, parse_mode=parse_mode)
        return SupplyResult.SUCCESSFULLY

    def _send_img_as_link(self, url, text):
        moded_text = '<a href="{url}">&#160;</a>{text}'.format(text=text, url=url)
        return self.send_text(moded_text,
                                disable_web_page_preview=False,
                                parse_mode='HTML')

    def send_img(self, url, ext, text, parse_mode=None):
        if len(text) > 200:
            logging.info('Long pic in {}.'.format(self.t_channel))
            return self._send_img_as_link(url, text)
        try:
            # Download and send as regular file
            filename = self._get_file_name(ext)
            if not download_file(url, filename):
                return SupplyResult.DO_NOT_WANT_THIS_SUBMISSION
            f = open(filename, 'rb')
            self.telepot_bot.sendPhoto(self.t_channel, f, caption=text, parse_mode=parse_mode)
            f.close()
            return SupplyResult.SUCCESSFULLY
        except TelegramError as e:
            logging.info('TelegramError prevented at {tc}.'.format(tc=self.t_channel))
            # No idea how to handle PHOTO_INVALID_DIMENSIONS :(
            return SupplyResult.SKIP_FOR_NOW

    def send_text(self, text, disable_web_page_preview=False, parse_mode=None):
        if len(text) < 4096:
            self.telepot_bot.sendMessage(self.t_channel, text,
                                            disable_web_page_preview=disable_web_page_preview,
                                            parse_mode=parse_mode)
            return SupplyResult.SUCCESSFULLY
        # If text is longer than 4096 symnols.
        next_text = text
        while len(next_text) > 0:
            new_text, next_text = self._split_4096(next_text)
            self.telepot_bot.sendMessage(self.t_channel, new_text,
                                            disable_web_page_preview=disable_web_page_preview,
                                            parse_mode=parse_mode)
            time.sleep(2)
        return SupplyResult.SUCCESSFULLY

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
            if num >= ALBUM_LIMIT:
                self.send_text('...')
                return SupplyResult.SUCCESSFULLY
            time.sleep(2)
        return SupplyResult.SUCCESSFULLY

    def send_simple(self, submission, **kwargs):
        '''
        Universal send method for most of the channels.

        Parameters
        ----------
        submission : praw.submission
            Reddit submission we are going to check.
        gif : boolean or formatted_string, optional
            False if this king of submissions is not needed.
            True (default) if default text if ok.
            formatted_string if special formatting is needed.
        img : description is same as for `gif`.
        album : description is same as for `gif`.
        text : description is same as for `gif`.
        other : description is same as for `gif`.
        check_dups : boolean, optional
            Will check whether submission content is duplicate or not.
        min_upvotes_limit : int, optional
            If specified, then only post higher that limit will be posted.
        max_selftext_len : max characters in self submission to be sent
        any other parameter : to be used in formatting.

        Returns
        -------
        SupplyResult
            Is submission posted to telegram or not.

        Raises
        ------
        Exception
            When exception.
        '''
        def human_format(num, round_to=1):
            magnitude = 0
            while abs(num) >= 1000:
                magnitude += 1
                num = round(num / 1000.0, round_to)
                if magnitude == 5:
                    break
            num = str(num)
            if magnitude == 0:
                while (num.endswith('0')) and ('.' in num):
                    num = num[0:-1]
                if num.endswith('.'):
                    num = num[0:-1]
            return '{n}{m}'.format(n=num, m=['', 'k', 'M', 'G', 'T', 'P'][magnitude])

        max_selftext_len = kwargs.get('max_selftext_len', -1)

        min_upvotes_limit = kwargs.get('min_upvotes_limit', None)
        if (min_upvotes_limit is not None) and (submission.score < min_upvotes_limit):
            return SupplyResult.SKIP_FOR_NOW

        try:
            what, url, ext = get_url(submission)
        except Exception as e:
            logging.info('HTTP fail prevented at {}!'.format(self.t_channel))
            return SupplyResult.SKIP_FOR_NOW

        formatters = {
            'what': what,
            'url': url,
            'ext': ext,
            'title': submission.title,
            'self_text': submission.selftext,
            'link': submission.url,
            'short_link': submission.shortlink,
            'subreddit_name': submission.subreddit,
            'score': submission.score,
            'upvotes': human_format(submission.score),
            'channel': self.t_channel,
            **kwargs
        }

        if kwargs.get('check_dups', False):
            # Check if there is a duplicate
            # If not — save content
            if self.dup_check_and_mark(url):
                # There is a duplicate
                return SupplyResult.DO_NOT_WANT_THIS_SUBMISSION

        if what == TYPE_GIF:
            what_to_do = kwargs.get('gif', True)
            if what_to_do:
                text = '{title}\n{short_link}\n{channel}'
                if isinstance(what_to_do, str):
                    text = what_to_do
                text = text.format(**formatters)
                return self.send_gif(url, ext, text)
            return SupplyResult.DO_NOT_WANT_THIS_SUBMISSION
        elif what == TYPE_IMG:
            what_to_do = kwargs.get('img', True)
            if what_to_do:
                text = '{title}\n{short_link}\n{channel}'
                if isinstance(what_to_do, str):
                    text = what_to_do
                text = text.format(**formatters)
                return self.send_img(url, ext, text)
            return SupplyResult.DO_NOT_WANT_THIS_SUBMISSION
        elif what == TYPE_ALBUM:
            what_to_do = kwargs.get('album', True)
            if what_to_do:
                text = '{title}\n{link}\n\n{short_link}\n{channel}'
                if isinstance(what_to_do, str):
                    text = what_to_do
                text = text.format(**formatters)
                self.send_text(text)
                return self.send_album(url)
            return SupplyResult.DO_NOT_WANT_THIS_SUBMISSION
        elif what == TYPE_TEXT:
            what_to_do = kwargs.get('text', True)
            if what_to_do:
                if max_selftext_len >= 0:
                    formatters['self_text'] = formatters['self_text'][:max_selftext_len]
                text = '{title}\n\n{self_text}\n\n{short_link}\n{channel}'
                if isinstance(what_to_do, str):
                    text = what_to_do
                text = text.format(**formatters)
                return self.send_text(text)
            return SupplyResult.DO_NOT_WANT_THIS_SUBMISSION
        elif what == TYPE_VIDEO:
            what_to_do = kwargs.get('video', True)
            if what_to_do:
                text = '{title}\n\n{short_link}\n{channel}'
                if isinstance(what_to_do, str):
                    text = what_to_do
                text = text.format(**formatters)
                return self.send_video(url, text)
            return SupplyResult.DO_NOT_WANT_THIS_SUBMISSION
        elif what == TYPE_OTHER:
            what_to_do = kwargs.get('other', True)
            if what_to_do:
                text = '{title}\n{link}\n\n{short_link}\n{channel}'
                if isinstance(what_to_do, str):
                    text = what_to_do
                text = text.format(**formatters)
                return self.send_text(text)
            return SupplyResult.DO_NOT_WANT_THIS_SUBMISSION
        else:
            return SupplyResult.DO_NOT_WANT_THIS_SUBMISSION
