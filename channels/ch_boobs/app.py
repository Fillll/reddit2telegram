#encoding:utf-8

import time

from utils import get_url


subreddit = 'boobs'
t_channel = '-1001052042617'


def send_post(submission, r2t):
    what, url, ext = get_url(submission)
    title = submission.title
    link = submission.short_link
    text = '{}\n{}'.format(title, link)

    if what in ('gif', 'img'):
        r2t.send_text('🔞🔞🔞🔞🔞🔞')
        time.sleep(10)
        return r2t.send_gif_img(what, url, ext, text)
    else:
        return False
