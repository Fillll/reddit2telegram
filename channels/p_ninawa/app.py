#encoding:utf-8

from utils import get_url, weighted_random_subreddit


t_channel = '-1001141585715'
subreddit = weighted_random_subreddit({
    'ahoge': 1,
    'awwnime': 1,
    'cutelittlefangs': 1,
    'ecchi': 1,
    'KanMusu': 1,
    'KanMusuNights': 1,
    'MoeStash': 1,
    'pantsu': 1,
    'pouts': 1,
    'Sukebei': 1,
    'twintails': 1,
    'tyingherhairup': 1,
    'wholesomeyuri': 1,
    'yuri': 1,
    'kemonomimi': 1,
    'inumimi': 1,
    'kitsunemimi': 1,
    'Nekomimi': 1,
    'Usagimimi': 1,
    'swimsuithentai': 1,
    'animebikinis': 1
})


def send_post(submission, r2t):
    what, url, ext = get_url(submission)
    title = submission.title
    link = submission.shortlink
    text = '{}\n\n/r/{}\n{}'.format(title, subreddit, link)

    if what == 'text':
        punchline = submission.selftext
        text = '{}\n\n{}\n\n/r/{}\n{}'.format(title, punchline, subreddit, link)
        return r2t.send_text(text)
    elif what == 'other':
        base_url = submission.url
        text = '{}\n{}\n\n/r/{}\n{}'.format(title, base_url, subreddit, link)
        return r2t.send_text(text)
    elif what == 'album':
        base_url = submission.url
        text = '{}\n{}\n\n/r/{}\n{}'.format(title, base_url, subreddit, link)
        r2t.send_text(text)
        #r2t.send_album(url)
        return True
    elif what in ('gif', 'img'):
        return r2t.send_gif_img(what, url, ext, text)
    else:
        return False
