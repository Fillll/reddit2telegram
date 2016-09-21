from urllib.parse import urlparse
import requests

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
    with open(filename, 'wb') as f:
        for chunk in r.iter_content(chunk_size=1024):
            if chunk:  # filter out keep-alive new chunks
                f.write(chunk)
                #f.flush() commented by recommendation from J.F.Sebastian
    return True
