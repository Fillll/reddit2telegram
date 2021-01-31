#encoding:utf-8

subreddit = 'wallstreetbets'
t_channel = '@wallstreetnewsitalia'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
