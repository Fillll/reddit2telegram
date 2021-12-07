#encoding:utf-8

subreddit = 'lost'
t_channel = '@lostbackup'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
