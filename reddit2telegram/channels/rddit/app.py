#encoding:utf-8

from utils import weighted_random_subreddit


subreddit = weighted_random_subreddit({
    'Cinemagraphs': 0.25,
    'BetterEveryLoop': 0.25,
    'interestingasfuck': 0.25,
    'gifs': 0.25
})
t_channel = '@rddit'


def send_post(submission, r2t):
    return r2t.send_simple(submission, check_dups=True,
        text=False,
        gif=True,
        img=True,
        album=True,
        other=False
    )
