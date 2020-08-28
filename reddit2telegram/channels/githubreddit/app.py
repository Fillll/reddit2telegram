#encoding:utf-8

subreddit = 'GitHub'
t_channel = '@GitHubReddit'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
