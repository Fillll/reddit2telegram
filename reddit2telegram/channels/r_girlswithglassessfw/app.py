#encoding:utf-8

subreddit = 'GirlsWithGlassesSFW'
t_channel = '@r_GirlsWithGlassesSFW'


submissions_ranking = 'new'
submissions_limit = 1000


def send_post(submission, r2t):
    return r2t.send_simple(submission)
