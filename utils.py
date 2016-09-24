# encoding:utf-8

from urllib.parse import urlparse
import requests


telegram_autoplay_limit = 10 * 1024 * 1024


def get_url(submission):
    url = submission.url
    # TODO: Better url validation
    if url.endswith('.gif'):
        return 'gif', url
    elif url.endswith('.gifv'):
        return 'gif', url[0:-1]
    elif urlparse(url).netloc == 'www.reddit.com':
        return 'text', None
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
