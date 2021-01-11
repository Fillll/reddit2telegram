#encoding:utf-8

from utils import SupplyResult


subreddit = 'lebanon'
t_channel = '@RLebanon'


def send_post(submission, r2t):
    if len(submission.comments.list()) < 40 and submission.score < 50:
        return SupplyResult.DO_NOT_WANT_THIS_SUBMISSION
    return r2t.send_simple(submission)
