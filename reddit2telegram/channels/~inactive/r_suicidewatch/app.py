#encoding:utf-8

subreddit = 'suicidewatch'
t_channel = '@r_suicidewatch'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
