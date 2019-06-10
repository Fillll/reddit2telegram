#encoding:utf-8

subreddit = 'theredpill+pussypass+pussypassdenied+mensrights'
t_channel = '@manpill'
submissions_ranking = 'new'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
