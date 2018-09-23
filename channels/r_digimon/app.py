#encoding:utf-8

subreddit = 'digimon'
t_channel = '@r_digimon'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
