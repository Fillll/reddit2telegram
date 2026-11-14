#encoding:utf-8

subreddit = 'Warzone'
t_channel = '@CallOfDutyWarzone_reddit'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
