#encoding:utf-8

subreddit = 'ik_ihe+tokkiefeesboek'
t_channel = '@r_ik_ihe'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
