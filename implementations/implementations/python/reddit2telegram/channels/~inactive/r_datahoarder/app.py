#encoding:utf-8

subreddit = 'datahoarder'
t_channel = '@r_DataHoarder'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
