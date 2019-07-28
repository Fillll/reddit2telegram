#encoding:utf-8

subreddit = 'DunderMifflin'
t_channel = '@DunderMiff'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
