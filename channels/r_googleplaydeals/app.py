#encoding:utf-8

from utils import get_url


t_channel = '@r_googleplaydeals'
subreddit = 'googleplaydeals'


def send_post(submission, r2t):
    what, url, ext = get_url(submission)
    title = submission.title
    link = submission.shortlink
    text = '{t}\n{l}'.format(t=title, l=link)

    if what == 'text':
        punchline = submission.selftext
        text = '{t}\n\n{p}\n\n{l}'.format(t=title, p=punchline, l=link)
        return r2t.send_text(text)
    elif what == 'other':
        base_url = submission.url
        text = '{t}\n{b}\n\n{l}'.format(t=title, b=base_url, l=link)
        return r2t.send_text(text)
    elif what == 'album':
        base_url = submission.url
        text = '{t}\n{b}\n\n{l}'.format(t=title, b=base_url, l=link)
        r2t.send_text(text)
        r2t.send_album(url)
        return True
    elif what in ('gif', 'img'):
        return r2t.send_gif_img(what, url, ext, text)
    else:
        return False
