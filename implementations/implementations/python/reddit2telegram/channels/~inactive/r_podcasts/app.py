#encoding:utf-8

subreddit = 'podcasts'
t_channel = '@r_Podcasts'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
