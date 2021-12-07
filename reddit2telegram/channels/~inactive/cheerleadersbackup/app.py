#encoding:utf-8

subreddit = 'cheerleaders'
t_channel = '@cheerleadersbackup'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
