#encoding:utf-8

subreddit = 'jenkinsci'
t_channel = '@jenkinsci'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
