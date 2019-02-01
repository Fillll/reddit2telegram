#encoding:utf-8

subreddit = 'animalromance'
t_channel = '@animalromance'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
