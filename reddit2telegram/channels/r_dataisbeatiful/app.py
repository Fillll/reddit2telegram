#encoding:utf-8

subreddit = 'dataisbeautiful'
t_channel = '@rdataisbeautiful'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
