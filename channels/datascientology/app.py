#encoding:utf-8

from utils import weighted_random_subreddit


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
    'JupyterNotebooks': 0.1,
    'data_irl': 0.55
})


def send_post(submission, r2t):
    return r2t.send_simple(submission,
        min_upvotes_limit=10,
        text='{title}\n\n{self_text}\n\n/r/{subreddit_name}\n{short_link}',
        gif='{title}\n\n/r/{subreddit_name}\n{short_link}',
        img='{title}\n\n/r/{subreddit_name}\n{short_link}',
        album='{title}\n{link}\n\n/r/{subreddit_name}\n{short_link}',
        other='{title}\n{link}\n\n/r/{subreddit_name}\n{short_link}'
    )
