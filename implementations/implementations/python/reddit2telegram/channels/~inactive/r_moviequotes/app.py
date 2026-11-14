#encoding:utf-8

subreddit = 'moviequotes'
t_channel = '@r_moviequotes'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
