#encoding:utf-8

subreddit = 'NewVegasMemes'
t_channel = '@noievegos'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
