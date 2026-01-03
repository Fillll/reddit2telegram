#encoding:utf-8

from utils import weighted_random_subreddit


t_channel = '@r_movies'
subreddit = weighted_random_subreddit({
    'MoviePosterPorn': 1,
    'CineShots': 1,
    'movies': 1,
})


def send_post(submission, r2t):
    return r2t.send_simple(submission)
