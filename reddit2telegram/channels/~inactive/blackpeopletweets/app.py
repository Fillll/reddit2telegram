#encoding:utf-8

subreddit = 'blackpeopletwitter'
t_channel = '@blackpeopletweets'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
