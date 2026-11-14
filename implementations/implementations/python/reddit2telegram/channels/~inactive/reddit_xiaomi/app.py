 #encoding:utf-8

subreddit = 'xiaomi'
t_channel = '@reddit_xiaomi'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
