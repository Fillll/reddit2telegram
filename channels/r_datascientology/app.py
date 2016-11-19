#encoding:utf-8

from utils import get_url, weighted_random_subreddit


t_channel = '@datascientology'
subreddit = weighted_random_subreddit({
    'dataisbeautiful': 8,
    'MapPorn': 5,
    'datasets': 1,
    'datascience': 2,
    'MachineLearning': 2,
    'visualization': 1,
    'Infographics': 2,
    'wordcloud': 0.7,
    'SampleSize': 0.7,
    'dataisugly': 1.2,
    'FunnyCharts': 0.6,
    'usdataisbeautiful': 0.2,
    'mathpics': 0.5,
    'statistics': 1,
    'pystats': 0.5,
    'opendata': 0.3,
    'bigdatajobs': 0.1,
    'bigdata': 0.2,
    'IPython': 0.1,
    'JupyterNotebooks': 0.1
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
        base_url = submission.url
        text = '{}\n{}\n\n/r/{}\n{}'.format(title, base_url, subreddit, link)
        return r2t.send_text(text)
    elif what == 'album':
        base_url = submission.url
        text = '{}\n{}\n\n/r/{}\n{}'.format(title, base_url, subreddit, link)
        r2t.send_text(text)
        r2t.send_album(url)
        return True
    elif what in ('gif', 'img'):
        return r2t.send_gif_img(what, url, ext, text)
    else:
        return False
