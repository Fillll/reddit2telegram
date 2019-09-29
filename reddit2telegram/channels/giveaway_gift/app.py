#encoding:utf-8

subreddit = 'giveaways'
t_channel = '@giveaway_gift'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
