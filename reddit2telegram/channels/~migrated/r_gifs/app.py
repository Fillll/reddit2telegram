#encoding:utf-8

from utils import get_url
from utils import SupplyResult

subreddit = 'gifs'
t_channel = '@r_gifs'


def send_post(submission, r2t):
    what, gif_url = get_url(submission)
    if what != 'gif':
        return SupplyResult.DO_NOT_WANT_THIS_SUBMISSION

    title = submission.title
    link = submission.shortlink

    if submission.over_18:
        url = submission.url
        text = '🛑NSFW🛑\n{}\n{}\n\n{}\n\nby @r_gifs'.format(url, title, link)
        return r2t.send_text(text, disable_web_page_preview=True)

    text = '{}\n{}\n\nby @r_gifs'.format(title, link)
    return r2t.send_gif(gif_url, text)
