#encoding:utf-8

import os

from utils import get_url, weighted_random_subreddit


subreddit = weighted_random_subreddit({
    'BeautifulFemales': 0.25,
    'cutegirlgifs': 0.25,
    'gentlemanboners': 0.25,
    'gentlemanbonersgifs': 0.25
})
t_channel = '@r_gentlemanboners'


def send_post(submission, r2t):
    title = submission.title
    link = submission.shortlink
    text = '{}\n{}'.format(title, link)
    what, url, ext = get_url(submission)
    return r2t.send_gif_img(what, url, ext, text)
