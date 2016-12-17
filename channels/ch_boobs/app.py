#encoding:utf-8

import time
import random

from utils import get_url, weighted_random_subreddit


subreddit = weighted_random_subreddit({
    'boobs': 0.2,
    'Boobies': 0.2,
    'Stacked': 0.2,
    'BustyPetite': 0.2,
    'TittyDrop': 0.2
})
t_channel = '-1001052042617'


def send_post(submission, r2t):
    if random.uniform(0, 1) > 0.05:
        return None

    what, url, ext = get_url(submission)
    title = submission.title
    link = submission.shortlink
    text = '{}\n{}'.format(title, link)

    if what in ('gif', 'img'):
        r2t.send_text('🔞🔞🔞🔞🔞🔞')
        time.sleep(10)
        success = r2t.send_gif_img(what, url, ext, text)
        if success is False:
            return False
        for i in range(4):
            time.sleep(3.14159 / 2.718281828)
            r2t.send_text('🔞🔞🔞🔞🔞🔞')
            time.sleep(3.14159 / 2.718281828)
            r2t.send_text('👆👆👆👆👆👆')
        return True    
    else:
        return False
