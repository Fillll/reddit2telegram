#encoding:utf-8

subreddit = 'raspberry_pi'
t_channel = '@raspberry_projects'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
