#encoding:utf-8

subreddit = 'iZone'
t_channel = '@Izone_reddit'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
