#encoding:utf-8

from utils import get_url, weighted_random_subreddit


t_channel = '@news756'
subreddit = weighted_random_subreddit({
    'politics': 0.5,
    'news': 0.5
})


def send_post(submission, r2t):
    what, url, ext = get_url(submission)
    title = submission.title
    link = submission.short_link
    text = '{}\n\n/r/{}\n{}'.format(title, subreddit, link)

    if what == 'text':
        punchline = submission.selftext
        text = '{}\n\n{}\n\n/r/{}\n{}'.format(title, punchline, subreddit, link)
        return r2t.send_text(text)
    elif what == 'other':
        url = submission.url
        text = '{}\n{}\n\n/r/{}\n{}'.format(title, url, subreddit, link)
        return r2t.send_text(text)
    elif what == 'album':
        url = submission.url
        text = '{}\n{}\n\n/r/{}\n{}'.format(title, url, subreddit, link)
        r2t.send_text(text)
        r2t.send_album(url)
        return True
    elif what in ('gif', 'img'):
        return r2t.send_gif_img(what, url, ext, text)
    else:
        return False
