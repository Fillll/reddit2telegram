#encoding:utf-8

from utils import get_url

subreddit = 'HighQualityGifs'
t_channel = '@r_HighQualityGifs'


def send_post(submission, r2t):
    what, gif_url, ext = get_url(submission)
    if what != 'gif':
        return False

    title = submission.title
    link = submission.shortlink

    text = '{}\n{}'.format(title, link)
    return r2t.send_gif(gif_url, ext, text)
