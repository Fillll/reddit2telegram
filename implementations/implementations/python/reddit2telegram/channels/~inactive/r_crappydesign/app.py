#encoding:utf-8

subreddit = 'crappydesign+crappydesign2'
t_channel = '@r_crappydesign'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
