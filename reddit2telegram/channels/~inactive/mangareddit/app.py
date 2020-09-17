#encoding:utf-8

subreddit = 'Manga'
t_channel = '@MangaReddit'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
