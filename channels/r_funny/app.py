#encoding:utf-8

import os

from utils import get_url


subreddit = 'funny'
t_channel = '@r_funny'


def send_post(submission, r2t):
    what, url, ext = get_url(submission)
    title = submission.title
    link = submission.short_link
    text = '{}\n{}'.format(title, link)

    if what == 'text':
        return False
    elif what == 'other':
        return False
    elif what == 'album':
        base_url = submission.url
        text = '{}\n{}\n\n{}'.format(title, base_url, link)
        r2t.send_text(text)
        r2t.send_album(url)
        return True
    elif what in ('gif', 'img'):
        return r2t.send_gif_img(what, url, ext, text)
    else:
        return False
