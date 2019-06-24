#encoding:utf-8

subreddit = 'DoctorWhumour'
t_channel = '@DoctorWhumour'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
