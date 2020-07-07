#encoding:utf-8

subreddit = 'news'
t_channel = '@news_reddit'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
