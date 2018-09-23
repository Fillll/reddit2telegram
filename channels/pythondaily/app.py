#encoding:utf-8

from utils import weighted_random_subreddit


t_channel = '@pythondaily'
subreddit = weighted_random_subreddit({
    'flask': 3,
    'Python': 6,
    'django': 4,
    'MachineLearning': 1,
    'djangolearning': 1,
    'IPython': 5,
    'pystats': 4,
    'JupyterNotebooks': 3
})


def send_post(submission, r2t):
    info = submission.selftext
    lwords = info.split(' ')[:200]
    words = ' '.join(lwords)
    return r2t.send_simple(submission,
        text='{title}\n\n' + words +'\n\n/r/{subreddit_name}\n{short_link}',
        gif='{title}\n\n/r/{subreddit_name}\n{short_link}',
        img='{title}\n\n/r/{subreddit_name}\n{short_link}',
        album='{title}\n{link}\n\n/r/{subreddit_name}\n{short_link}',
        other='{title}\n{link}\n\n/r/{subreddit_name}\n{short_link}'
    )
