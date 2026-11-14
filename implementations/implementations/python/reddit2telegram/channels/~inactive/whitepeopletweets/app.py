#encoding:utf-8

subreddit = 'whitepeopletwitter'
t_channel = '@whitepeopletweets'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
