#encoding:utf-8

subreddit = 'TheVampireDiaries'
t_channel = '@TheVampireDiariesbackup'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
