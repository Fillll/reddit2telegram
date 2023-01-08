#encoding:utf-8

from utils import weighted_random_subreddit


t_channel = '@datascientology'
subreddit = weighted_random_subreddit({
    'MachineLearning': 1,
    'LanguageTechnology': 1,
    'deeplearning': 1,
    'computervision': 1,
})


def send_post(submission, r2t):
    return r2t.send_simple(submission,
        min_upvotes_limit=10,
        text='{title}\n\n{self_text}\n\n/r/{subreddit_name}\n{short_link}',
        gif='{title}\n\n/r/{subreddit_name}\n{short_link}',
        video='{title}\n\n/r/{subreddit_name}\n{short_link}',
        img='{title}\n\n/r/{subreddit_name}\n{short_link}',
        album='{title}\n{link}\n\n/r/{subreddit_name}\n{short_link}',
        other='{title}\n{link}\n\n/r/{subreddit_name}\n{short_link}'
    )
