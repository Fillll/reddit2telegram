#encoding:utf-8

from utils import get_url, weighted_random_subreddit


subreddit = weighted_random_subreddit({
    'Cinemagraphs': 0.25,
    'BetterEveryLoop': 0.25,
    'interestingasfuck': 0.25,
    'gifs': 0.25
})
t_channel = '@rddit'


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
        base_url = submission.url
        text = '{}\n{}\n\n{}'.format(title, base_url, link)
        r2t.send_text(text)
        r2t.send_album(url)
        return True
    elif what in ('gif', 'img'):
        if r2t.dup_check_and_mark(url) is True:
            return False
        return r2t.send_gif_img(what, url, ext, text)
    else:
        return False
