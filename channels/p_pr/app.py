#encoding:utf-8

from utils import get_url, weighted_random_subreddit


t_channel = '-1001105843457'
subreddit = weighted_random_subreddit({
    'anal': 1,
    'ConfusedBoners': 1,
    'NSFWFunny': 1,
    'porn_irl': 1,
    'ImGoingToHellForThis': 1,
    'WTF': 1
})


def send_post(submission, r2t):
    what, url, ext = get_url(submission)
    title = submission.title
    link = submission.shortlink
    text = '{}\n\n/r/{}\n{}'.format(title, subreddit, link)

    if what == 'album':
        base_url = submission.url
        text = '{}\n{}\n\n/r/{}\n{}'.format(title, base_url, subreddit, link)
        r2t.send_text(text)
        r2t.send_album(url)
        return True
    return r2t.send_gif_img(what, url, ext, text)
