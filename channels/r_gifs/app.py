#encoding:utf-8

import os

import requests


subreddit = 'gifs'
t_channel = '@r_gifs'


def get_url(submission):
    url = submission.url
    # TODO: Better url validation
    if url.endswith('.gif'):
        return url
    elif url.endswith('.gifv'):
        return url[0:-1]
    else:
        return None


def download_file(url):
    # http://stackoverflow.com/questions/16694907/how-to-download-large-file-in-python-with-requests-py
    # NOTE the stream=True parameter
    r = requests.get(url, stream=True)
    with open('r_gifs.gif', 'wb') as f:
        for chunk in r.iter_content(chunk_size=1024): 
            if chunk:  # filter out keep-alive new chunks
                f.write(chunk)
                #f.flush() commented by recommendation from J.F.Sebastian
    return True


def send_post(submission, bot):
    gif_url = get_url(submission)
    if gif_url is None:
        return False
    # Download gif
    download_file(gif_url)
    # Telegram will not autoplay big gifs
    if os.path.getsize('r_gifs.gif') > 10 * 1024 * 1024:
        return False
    title = submission.title
    link = submission.short_link
    text = '%s\n%s\n\nby @r_gifs' % (title, link)
    f = open('r_gifs.gif', 'rb')
    bot.sendDocument(t_channel, f, caption=text)
    f.close()
    return True
