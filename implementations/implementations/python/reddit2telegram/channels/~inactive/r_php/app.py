#encoding:utf-8

subreddit = 'PHP+laravel+symfony'
t_channel = '@r_php'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
