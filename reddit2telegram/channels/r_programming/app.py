#encoding:utf-8

subreddit = 'Programming'
t_channel = '@r_Pr0gramming'


def send_post(submission, r2t):
    return r2t.send_simple(submission, min_upvotes_limit=10)
