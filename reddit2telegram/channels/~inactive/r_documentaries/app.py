#encoding:utf-8

subreddit = 'documentaries'
t_channel = '@r_documentaries'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
