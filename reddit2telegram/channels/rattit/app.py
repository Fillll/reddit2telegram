#encoding:utf-8

subreddit = 'RATS'
t_channel = '@Rattit'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
