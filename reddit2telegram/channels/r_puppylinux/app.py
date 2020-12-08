#encoding:utf-8

subreddit = 'puppylinux'
t_channel = '@r_PuppyLinux'


submissions_ranking = 'new'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
