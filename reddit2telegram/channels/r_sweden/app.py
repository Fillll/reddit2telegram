#encoding:utf-8

subreddit = 'sweden'
t_channel = '@r_sweden'


def send_post(submission, r2t):
    return r2t.send_simple(submission, nsfw_filter_out=False)