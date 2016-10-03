# encoding:utf-8

from urllib.parse import urlparse
import requests
import yaml

from imgurpython import ImgurClient


telegram_autoplay_limit = 10 * 1024 * 1024


def get_url(submission):
    url = submission.url
    # TODO: Better url validation
    if url.endswith('.gif'):
        # Just plain gif
        return 'gif', url
    elif url.endswith('.gifv'):
        return 'gif', url[0:-1]
    elif submission.is_self is True:
        # Self submission with text
        return 'text', None
    elif urlparse(url).netloc == 'imgur.com':
        # Imgur
        imgur_config = yaml.load(open('imgur.yml').read())
        imgur_client = ImgurClient(imgur_config['client_id'], imgur_config['client_secret'])
        path_parts = urlparse(url).path.split('/')
        if path_parts[1] != 'a':
            # Not an imgur album
            img = imgur_client.get_image(path_parts[1])
            if img.animated is False:
                return 'other', img.link
            else:
                return 'gif', img.link
        elif path_parts[1] == 'a':
            # An imgur album
            album = imgur_client.get_album(path_parts[2])
            story = {'behind': {}, 'gifs': {}}
            for num, img in enumerate(album.images):
                number = num + 1
                if img['animated'] is False:
                    story['behind'][number] = img['link']
                else:
                    story['gifs'][number] = img['link']
            return 'album', story

    else:
        return 'other', url


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
