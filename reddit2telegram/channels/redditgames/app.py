#encoding:utf-8

subreddit = 'Games'
t_channel = '@RedditGames'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
