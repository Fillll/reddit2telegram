#encoding:utf-8

subreddit = 'linux_gaming'
t_channel = '@LinuxGamingx'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
