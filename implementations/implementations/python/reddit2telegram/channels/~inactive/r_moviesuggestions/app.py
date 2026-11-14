#encoding:utf-8

subreddit = 'moviesuggestions'
t_channel = '@r_moviesuggestions'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
