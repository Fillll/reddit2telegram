#encoding:utf-8

subreddit = 'LifeProTips'
t_channel = '@r_lifeprotips'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
