#encoding:utf-8

from utils import get_url
from utils import SupplyResult


t_channel = '@reddit_all'
subreddit = 'all'


def send_post(submission, r2t):
    upvotes = submission.score
    if upvotes < 10000:
        return SupplyResult.SKIP_FOR_NOW

    return r2t.send_simple(submission,
        text='{title}\n\n{self_text}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{short_link}',
        other='{title}\n{link}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{short_link}',
        album='{title}\n{link}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{short_link}',
        gif='{title}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{short_link}',
        img='{title}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{short_link}'
    )
