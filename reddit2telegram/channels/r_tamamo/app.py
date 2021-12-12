#encoding:utf-8

from utils import weighted_random_subreddit


subreddit = weighted_random_subreddit({
    'tamamo': 1.0,
})
t_channel = '@r_tamamo'


def send_post(submission, r2t):
    return r2t.send_simple(submission, nsfw_filter_out=True,
        min_upvotes_limit=5,
        text=False,
        gif=True,
        video=True,
        img=True,
        album=True,
        other=False
    )
