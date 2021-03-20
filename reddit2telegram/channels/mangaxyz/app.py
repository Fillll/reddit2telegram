#encoding:utf-8

subreddit = 'manga+MangaFrames'
t_channel = '@mangaxyz'


def send_post(submission, r2t):
    return r2t.send_simple(submission, min_upvotes_limit=100)
