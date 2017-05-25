#encoding:utf-8

from utils import get_url


t_channel = '@reddit_all'
subreddit = 'all'


def send_post(submission, r2t):
    what, url, ext = get_url(submission)
    title = submission.title
    link = submission.shortlink
    sub = submission.subreddit
    upvotes = submission.score

    if what == 'text':
        punchline = submission.selftext
        text = '{title}\n\n{main_text}\n\n{votes} upvotes\n/r/{subreddit}\n{link}'.format(
            title=title,
            main_text=punchline,
            subreddit=sub,
            link=link,
            votes=upvotes)
        return r2t.send_text(text)

    if what == 'other':
        base_url = submission.url
        text = '{title}\n{base_url}\n\n{votes} upvotes\n/r/{subreddit}\n{link}'.format(
            title=title,
            base_url=base_url,
            subreddit=sub,
            link=link,
            votes=upvotes)
        return r2t.send_text(text)

    if what == 'album':
        base_url = submission.url
        text = '{title}\n{base_url}\n\n{votes} upvotes\n/r/{subreddit}\n{link}'.format(
            title=title,
            base_url=base_url,
            subreddit=sub,
            link=link,
            votes=upvotes)
        r2t.send_text(text)
        r2t.send_album(url)
        return True

    if what in ('gif', 'img'):
        text = '{title}\n\n{votes} upvotes\n/r/{subreddit}\n{}link'.format(
            title=title,
            subreddit=sub,
            link=link,
            votes=upvotes)
        return r2t.send_gif_img(what, url, ext, text)

    return False
