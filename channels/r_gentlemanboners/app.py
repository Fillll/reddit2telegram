#encoding:utf-8

from utils import weighted_random_subreddit


subreddit = weighted_random_subreddit({
    'BeautifulFemales': 0.25,
    'cutegirlgifs': 0.25,
    'gentlemanboners': 0.25,
    'gentlemanbonersgifs': 0.25
})
t_channel = '@r_gentlemanboners'


def send_post(submission, r2t):
    return r2t.send_simple(submission,
        text=False,
        gif=True,
        img=True,
        album=False,
        other=False
    )
