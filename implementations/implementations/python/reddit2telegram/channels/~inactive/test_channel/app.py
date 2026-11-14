#encoding:utf-8

subreddit = 'all'
t_channel = '@r_channels_test'
submissions_ranking = 'top'
submissions_limit = 1000


def send_post(submission, r2t):
    # 1/0
    return r2t.send_simple(submission)
