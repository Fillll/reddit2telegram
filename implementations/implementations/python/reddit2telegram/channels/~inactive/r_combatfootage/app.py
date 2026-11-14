#encoding:utf-8

subreddit = 'CombatFootage'
t_channel = '@r_combatfootage'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
