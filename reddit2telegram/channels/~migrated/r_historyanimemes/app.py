#encoding:utf-8

subreddit = 'HistoryAnimemes'
t_channel = '@r_HistoryAnimemes'
submissions_ranking = 'new'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
