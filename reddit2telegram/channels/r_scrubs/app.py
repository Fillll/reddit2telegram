#encoding:utf-8

subreddit = 'Scrubs'
t_channel = '@r_scrubs'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
