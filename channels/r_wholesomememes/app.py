#encoding:utf-8

from utils import get_url, weighted_random_subreddit

t_channel = '@r_wholesomememes'
subreddit = 'wholesomeMemes+wholesomeAnimemes+wholesomeGifs+wholesomeComics'

def send_post(submission, r2t):
    what, url, ext = get_url(submission)
    title = submission.title
    link = submission.shortlink
    text = '{}\n{}'.format(title, link)

    if what in ('gif', 'img'):
        if r2t.dup_check_and_mark(url):
            return False
        return r2t.send_gif_img(what, url, ext, text)
    elif what == 'album':
        base_url = submission.url
        text = '{}\n{}\n\n{}'.format(title, base_url, link)
        r2t.send_text(text)
        r2t.send_album(url)
        return True
    else:
        r2t.send_text(text)
