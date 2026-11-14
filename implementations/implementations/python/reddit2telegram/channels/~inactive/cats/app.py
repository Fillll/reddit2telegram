#encoding:utf-8

from utils import weighted_random_subreddit


t_channel = '@RedditCats'
subreddit = weighted_random_subreddit({
    'cats': 1,
    'StartledCats': 1,
    'CatsStandingUp': 1,
    'funny_cats': 1,
    'catpictures': 1,
    'CatSlaps': 1,
    'CatsAreAssholes': 1,
    'teefies': 1,
    'CatGifs': 1,
    'BigCatGifs': 1,
    'catreactiongifs': 1,
    'kittyhugs': 1,
    'kittyhugs': 1,
    'FunnyCatGifs': 1,
    'LazyCats': 1,
    'catsinboxes': 1,
    'CatHighFive': 1,
    'cathug': 1,
    'WigglyCats': 1,
    'catfreakouts': 1,
    'catremakesofmovies': 1
})


def send_post(submission, r2t):
    return r2t.send_simple(submission,
        text=False,
        gif=True,
        img=True,
        other=False,
        album=True
    )
