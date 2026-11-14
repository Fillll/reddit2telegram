#encoding:utf-8

subreddit = 'IdiotsInCars'
t_channel = '@Idiots_In_Cars'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
