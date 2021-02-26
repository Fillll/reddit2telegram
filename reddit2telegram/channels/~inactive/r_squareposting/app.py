#encoding:utf-8

subreddit = 'SquarePosting'
t_channel = '@r_squareposting'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
