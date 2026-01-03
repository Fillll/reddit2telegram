#encoding:utf-8

subreddit = 'tupac'
t_channel = '@r_tupac'


submissions_ranking = 'new'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
