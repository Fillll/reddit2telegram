#encoding:utf-8

subreddit = 'udemyfreebies'
t_channel = '@r_udemyfreebies'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
