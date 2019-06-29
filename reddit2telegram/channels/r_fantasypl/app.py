#encoding:utf-8

subreddit = 'FantasyPL'
t_channel = '@r_FantasyPL'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
