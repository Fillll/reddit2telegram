#encoding:utf-8

subreddit = 'hyderabad'
t_channel = '@rhyderabad'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
