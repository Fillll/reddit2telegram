#encoding:utf-8

subreddit = 'ImaginaryWastelands+ImaginaryCityscapes+ImaginaryPathways+ImaginaryWorlds+ImaginaryBattlefields+ImaginaryWildlands'
t_channel = '@imaginarylands'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
