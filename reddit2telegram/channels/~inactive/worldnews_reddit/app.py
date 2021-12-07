#encoding:utf-8

subreddit = 'worldnews'
t_channel = '@worldnews_reddit'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
