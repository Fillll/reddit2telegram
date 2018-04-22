#encoding:utf-8

from utils import get_url
from utils import SupplyResult


subreddit = 'ProgrammerHumor'
t_channel = '@programmer_humor'


def send_post(submission, r2t):
    what, url, ext = get_url(submission)
    if what not in ('gif', 'img'):
        return SupplyResult.DO_NOT_WANT_THIS_SUBMISSION

    title = submission.title
    link = submission.shortlink

    if submission.over_18:
        url = submission.url
        text = '🔞NSFW🔞\n{u}\n{t}\n\n{l}\n\nby {c}'.format(
            u=url,
            t=title,
            l=link,
            c=t_channel)
        return r2t.send_text(text, disable_web_page_preview=True)

    text = '{t}\n{l}\n\nby {c}'.format(
        t=title,
        l=link,
        c=t_channel)
    return r2t.send_gif_img(what, url, ext, text)
