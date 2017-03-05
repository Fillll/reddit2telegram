#encoding:utf-8

from utils import get_url


subreddit = 'dankmemes'
t_channel = '@r_dankmemes'


def send_post(submission, r2t):
    what, url, ext = get_url(submission)

    title = submission.title
    link = submission.shortlink
    text = '{}\n{}'.format(title, link)

    if what == 'text':
        return False
    elif what == 'other':
        return False
    elif what == 'album':
        return False
    elif what in ('gif', 'img'):
        if r2t.dup_check_and_mark(url) is True:
            return False
        return r2t.send_gif_img(what, url, ext, text)
    else:
        return False
