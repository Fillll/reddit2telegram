#encoding:utf-8

subreddit = 'IngressPrimeFeedback'
t_channel = '@IngressPrimeFeedback'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
