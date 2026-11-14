#encoding:utf-8

subreddit = 'shitpostxiv'
t_channel = '@r_ShitpostXIV'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
