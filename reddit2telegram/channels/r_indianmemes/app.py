#encoding:utf-8

from utils import SupplyResult


subreddit = 'IndianMeyMeys+IndianDankMemes+desimemes+TheRawKnee+indiamemeHindiMemes'
t_channel = '@r_indianmemes'


def send_post(submission, r2t):
    # What to skip
    if submission.subreddit.display_name == 'TheRawKnee' and submission.link_flair_text != 'Sirf Meme (Non-Rawknee) :D':
        return SupplyResult.DO_NOT_WANT_THIS_SUBMISSION

    return r2t.send_simple(submission,
        text=False,
        gif=False,
        img=True,
        album=False,
        other=False
    )
