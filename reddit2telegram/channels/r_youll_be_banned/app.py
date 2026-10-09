#encoding:utf-8

SUBREDDITS = (
    'youll_be_banned',
    'no_or_youll_be_banned',
    'Youll_Myabe_Be_Banned',
    'yes_or_youllbe_banned',
    'YesOrNoYouWontGetABan',
    'YoBanMe',
)


subreddit = '+'.join(SUBREDDITS)
t_channel = '@r_youll_be_banned'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
