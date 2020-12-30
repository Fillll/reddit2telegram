#encoding:utf-8

subreddit = 'WhatsWrongWithYourDog'
t_channel = '@WhatsWrongWithYourDog'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
