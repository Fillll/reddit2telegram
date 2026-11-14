#encoding:utf-8

subreddit = 'blursedimages+cursedcomments+MemeEconomy'
t_channel = '@mereddit'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
