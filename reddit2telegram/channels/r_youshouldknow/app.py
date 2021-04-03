#encoding:utf-8

subreddit = 'YouShouldKnow+LifeProTips+lifehacks'
t_channel = '@r_youshouldknow'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
