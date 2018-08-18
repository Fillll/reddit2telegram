#encoding:utf-8

from utils import weighted_random_subreddit


t_channel = '@news756'
subreddit = weighted_random_subreddit({
    'politics': 0.5,
    'news': 0.5
})


def send_post(submission, r2t):
    return r2t.send_simple(submission,
        text='{title}\n\n{self_text}\n\n/r/{subreddit_name}\n{short_link}',
        gif='{title}\n\n/r/{subreddit_name}\n{short_link}',
        img='{title}\n\n/r/{subreddit_name}\n{short_link}',
        album='{title}\n{link}\n\n/r/{subreddit_name}\n{short_link}',
        other='{title}\n{link}\n\n/r/{subreddit_name}\n{short_link}'
    )
