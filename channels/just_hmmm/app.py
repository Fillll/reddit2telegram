#encoding:utf-8

from utils import get_url, weighted_random_subreddit

subreddit = weighted_random_subreddit({
    'hmmmgifs': 1/3,
    'hmmm': 2/3
})
t_channel = '@just_hmmm'


def send_post(submission, r2t):
    what, url, ext = get_url(submission)
    if what not in ('gif', 'img'):
        return False

    title = submission.title
    link = submission.shortlink

    if submission.over_18:
        url = submission.url
        text = 'NSFW\n{}\n{}\n\n{}\n\nby @just_hmmm'.format(url, title, link)
        return r2t.send_text(text, disable_web_page_preview=True)

    text = '{}\n{}\n\nby @just_hmmm'.format(title, link)
    return r2t.send_gif_img(what, url, ext, text)
