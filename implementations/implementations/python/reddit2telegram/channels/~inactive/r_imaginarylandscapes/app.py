#encoding:utf-8

subreddit = 'ImaginaryLandscapes'
t_channel = '@r_imaginarylandscapes'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
