#encoding:utf-8

subreddit = 'simpsonsshitposting'
t_channel = '@r_simpsonshitpost'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
