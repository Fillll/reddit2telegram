#encoding:utf-8

import time

from utils import get_url, weighted_random_subreddit


main_channel = '-1001052042617'
fake_channel = '@r_channels_test'


t_channel = weighted_random_subreddit({
    main_channel: 0.05,
    fake_channel: 0.95
})
subreddit = 'boobs' if t_channel == main_channel else 'all'


def send_post(submission, r2t):
    what, url, ext = get_url(submission)
    title = submission.title
    link = submission.short_link
    text = '{}\n{}'.format(title, link)

    if t_channel == 'boobs':
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
    else:
        text = '{}\n\n/r/{}\n{}'.format(title, submission.subreddit, link)
        if what == 'text':
            punchline = submission.selftext
            text = '{}\n\n{}\n\n/r/{}\n{}'.format(title, punchline, subreddit, link)
            return r2t.send_text(text)
        elif what == 'other':
            base_url = submission.url
            text = '{}\n{}\n\n/r/{}\n{}'.format(title, base_url, subreddit, link)
            return r2t.send_text(text)
        elif what == 'album':
            base_url = submission.url
            text = '{}\n{}\n\n/r/{}\n{}'.format(title, base_url, subreddit, link)
            r2t.send_text(text)
            r2t.send_album(url)
            return True
        elif what in ('gif', 'img'):
            return r2t.send_gif_img(what, url, ext, text)
        else:
            return False
