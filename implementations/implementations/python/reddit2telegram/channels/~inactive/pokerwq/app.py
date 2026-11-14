#encoding:utf-8

subreddit = 'poker'
t_channel = '@PokerWQ'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
