#encoding:utf-8

from utils import weighted_random_subreddit


subreddit = weighted_random_subreddit({
    'slygifs': 1,
    'WastedGifs': 1,
    'SFWPornGifs': 1,
    'NatureGifs': 1,
    'reversegif': 1,
    'EarthPornGifs': 1,
    'AnimalPornGifs': 1,
})
t_channel = '@gifsgalore'


def send_post(submission, r2t):
    return r2t.send_simple(submission,
        text=False,
        gif=True,
        img=False,
        album=False,
        other=False
    )
