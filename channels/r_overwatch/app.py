#encoding:utf-8

from utils import get_url

subreddit = 'overwatch'
t_channel = '@r_overwatch'


def send_post(submission, r2t):
    what, gif_url, ext = get_url(submission)
    if what != 'gif':
        return False

    title = submission.title
    link = submission.shortlink

    text = '{}\n{}\n\nby @r_overwatch'.format(title, link)
    return r2t.send_gif(gif_url, ext, text)
