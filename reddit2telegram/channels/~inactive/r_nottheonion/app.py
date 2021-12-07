#encoding:utf-8

subreddit = 'nottheonion'
t_channel = '@r_nottheonion'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
