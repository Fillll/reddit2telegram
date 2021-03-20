#encoding:utf-8

subreddit = 'replayfootball'
t_channel = '@r_replayfootball'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
