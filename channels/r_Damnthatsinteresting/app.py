#encoding:utf-8

# Write here subreddit name. Like this one for /r/Damnthatsinteresting.
subreddit = 'Damnthatsinteresting'
# This is for your public telegram channel.
t_channel = '@r_Damnthatsinteresting'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
