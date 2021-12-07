#encoding:utf-8

subreddit = 'moviescirclejerk'
t_channel = '@r_moviescirclejerk'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
