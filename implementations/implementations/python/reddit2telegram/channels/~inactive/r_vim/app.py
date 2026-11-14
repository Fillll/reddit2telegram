#encoding:utf-8

subreddit = 'vim'
t_channel = '@r_vim'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
