#encoding:utf-8

subreddit = 'confidentlyincorrect'
t_channel = '@r_confidentlyincorrect'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
