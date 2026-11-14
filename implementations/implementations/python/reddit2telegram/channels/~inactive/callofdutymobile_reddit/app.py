#encoding:utf-8

subreddit = 'CallOfDutyMobile'
t_channel = '@CallOfDutyMobile_reddit'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
