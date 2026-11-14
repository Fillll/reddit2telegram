#encoding:utf-8

subreddit = 'DotA2'
t_channel = '@reddit_Dota2'


def send_post(submission, r2t):
    return r2t.send_simple(submission,
        min_upvotes_limit=500
    )
