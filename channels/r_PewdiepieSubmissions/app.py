#encoding:utf-8

subreddit = 'PewdiepieSubmissions'
t_channel = '@r_PewdiepieSubmissions'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
