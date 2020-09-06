#encoding:utf-8

subreddit = 'PoliticalCompassMemes'
t_channel = '@r_PoliticalCompassMemes'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
