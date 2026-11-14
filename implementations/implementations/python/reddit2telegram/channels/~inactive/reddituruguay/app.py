#encoding:utf-8

subreddit = 'uruguay'
t_channel = '@reddituruguay'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
