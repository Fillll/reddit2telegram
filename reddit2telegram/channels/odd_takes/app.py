#encoding:utf-8

subreddit = 'The10thDentist'
t_channel = '@odd_takes'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
