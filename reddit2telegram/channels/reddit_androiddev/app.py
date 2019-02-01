#encoding:utf-8

subreddit = 'androiddev'
t_channel = '@reddit_androiddev'


def send_post(submission, r2t):
    return r2t.send_simple(submission, max_selftext_len=500)
