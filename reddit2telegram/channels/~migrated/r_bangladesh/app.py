#encoding:utf-8

subreddit = 'bangladesh'
t_channel = '@r_bangladesh'


submissions_ranking = 'new'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
