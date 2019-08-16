#encoding:utf-8

subreddit = 'shittyaskscience'
t_channel = '@ShitScience'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
