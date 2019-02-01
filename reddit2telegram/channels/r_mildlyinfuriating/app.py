#encoding:utf-8

subreddit = 'mildlyinfuriating'
t_channel = '@r_mildlyinfuriating'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
