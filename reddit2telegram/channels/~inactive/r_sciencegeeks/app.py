#encoding:utf-8

subreddit = 'science'
t_channel = '@r_sciencegeeks'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
