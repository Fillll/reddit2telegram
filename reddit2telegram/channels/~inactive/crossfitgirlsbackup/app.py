#encoding:utf-8

subreddit = 'CrossfitGirls'
t_channel = '@CrossfitGirlsbackup'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
