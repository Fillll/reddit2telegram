#encoding:utf-8

subreddit = 'fightporn'
t_channel = '@r_fightporn'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
