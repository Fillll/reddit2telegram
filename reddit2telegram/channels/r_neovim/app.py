#encoding:utf-8

subreddit = 'neovim'
t_channel = '@r_neovim'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
