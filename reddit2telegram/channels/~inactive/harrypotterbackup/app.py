#encoding:utf-8

subreddit = 'harrypotter'
t_channel = '@harrypotterbackup'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
