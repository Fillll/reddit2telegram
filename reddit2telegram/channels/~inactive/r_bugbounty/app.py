#encoding:utf-8

subreddit = 'bugbounty'
t_channel = '@r_bugbounty'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
