#encoding:utf-8

subreddit = 'books'
t_channel = '@r_books'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
