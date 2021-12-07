#encoding:utf-8

subreddit = 'MoviePosterPorn'
t_channel = '@MoviePosterTG'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
