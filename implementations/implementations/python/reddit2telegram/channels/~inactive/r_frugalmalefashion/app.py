#encoding:utf-8

subreddit = 'frugalmalefashion'
t_channel = '@r_frugalmalefashion'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
