#encoding:utf-8

subreddit = 'PoliticalHumor+PoliticalCompassMemes'
t_channel = '@r_PoliticalMemes'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
