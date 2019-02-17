#encoding:utf-8

import importlib
import random
from datetime import datetime

from utils import SupplyResult
from utils.tech import get_all_public_submodules


def what_submodule():
    all_submodules = get_all_public_submodules()
    all_submodules.remove('reddit2telegram')
    return random.choice(all_submodules)

def what_subreddit(submodule_name_to_promte):
    submodule_to_promote = importlib.import_module('channels.{}.app'.format(submodule_name_to_promte))
    return submodule_to_promote.subreddit


def what_channel(submodule_name_to_promte):
    submodule_to_promote = importlib.import_module('channels.{}.app'.format(submodule_name_to_promte))
    return submodule_to_promote.t_channel


submodule_name_to_promte = what_submodule()


subreddit = what_subreddit(submodule_name_to_promte)
t_channel = '@reddit2telegram'
submissions_ranking = 'top'
submissions_limit = 1000


def send_post(submission, r2t):
    now = datetime.now()
    today = datetime(now.year, now.month, now.day)
    random_number = abs(hash(today))
    if (now.hour != random_number % 24) or (now.minute != random_number % 45):
        return SupplyResult.STOP_THIS_SUPPLY

    submission.title  # to make it non-lazy
    return r2t.send_simple(submission,
        channel_to_promote=what_channel(submodule_name_to_promte),
        date=datetime.utcfromtimestamp(submission.created_utc).strftime('%Y %b %d'),
        text='{title}\n\n{self_text}\n\n{upvotes} upvotes\n/r/{subreddit_name} on {date}\n{short_link}\n{channel_to_promote}',
        other='{title}\n{link}\n\n{upvotes} upvotes\n/r/{subreddit_name} on {date}\n{short_link}\n{channel_to_promote}',
        album='{title}\n{link}\n\n{upvotes} upvotes\n/r/{subreddit_name} on {date}\n{short_link}\n{channel_to_promote}',
        gif='{title}\n\n{upvotes} upvotes\n/r/{subreddit_name} on {date}\n{short_link}\n{channel_to_promote}',
        img='{title}\n\n{upvotes} upvotes\n/r/{subreddit_name} on {date}\n{short_link}\n{channel_to_promote}'
    )
