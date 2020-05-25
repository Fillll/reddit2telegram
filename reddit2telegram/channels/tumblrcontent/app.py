#encoding:utf-8

subreddit = 'tumblr'
t_channel = '@Tumblrcontent'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
