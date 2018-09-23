#encoding:utf-8

# Write here subreddit name. Like this one for /r/BigAnimeTiddies.
subreddit = 'BigAnimeTiddies'
# This is for your public telegram channel.
t_channel = '@r_BigAnimeTiddies'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
