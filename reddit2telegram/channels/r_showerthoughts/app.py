#encoding:utf-8

from utils import get_url
from utils import SupplyResult


subreddit = 'Showerthoughts'
t_channel = '@r_Showerthoughts'


def send_post(submission, r2t):
    what, _ = get_url(submission)
    if what != 'text':
        return SupplyResult.DO_NOT_WANT_THIS_SUBMISSION
    if submission.score < 111:
        return SupplyResult.SKIP_FOR_NOW
    texts = [submission.title]
    punchline = submission.selftext.strip()
    if len(punchline) > 0:
        texts.append(punchline)
    main_text = '\n\n'.join(texts)
    link = submission.shortlink
    text = '{main}\n\n{link}'.format(
            main=main_text, link=link)
    return r2t.send_text(text, disable_web_page_preview=True)
