#encoding:utf-8

subreddit = 'tf_irl'
t_channel = '@r_tfirl'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
