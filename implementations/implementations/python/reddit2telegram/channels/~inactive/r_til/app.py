#encoding:utf-8

t_channel = '@r_til'
subreddit = 'todayilearned'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
