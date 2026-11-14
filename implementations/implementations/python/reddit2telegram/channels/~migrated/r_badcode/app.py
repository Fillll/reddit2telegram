#encoding:utf-8

subreddit = 'badcode'
t_channel = '@r_badcode'


submissions_ranking = 'new'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
