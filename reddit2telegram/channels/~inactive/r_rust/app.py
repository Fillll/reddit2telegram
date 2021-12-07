# encoding:utf-8

subreddit = "rust"
t_channel = "@r_rust"


def send_post(submission, r2t):
    return r2t.send_simple(submission)
