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
