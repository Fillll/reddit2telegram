#encoding:utf-8

subreddit = 'YoutubeCompendium'
t_channel = '@YoutubeCompendium'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
