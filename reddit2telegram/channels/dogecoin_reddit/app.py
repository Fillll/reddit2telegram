#encoding:utf-8

subreddit = 'dogecoin'
t_channel = '@dogecoin_reddit'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
