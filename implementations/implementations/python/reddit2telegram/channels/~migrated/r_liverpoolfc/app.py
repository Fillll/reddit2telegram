#encoding:utf-8

subreddit = 'LiverpoolFC'
t_channel = '@r_LiverpoolFC'


def send_post(submission, r2t):
    return r2t.send_simple(submission, min_upvotes_limit=100, check_dups=True)
