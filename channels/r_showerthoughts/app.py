#encoding:utf-8

from utils import get_url


subreddit = 'Showerthoughts'
t_channel = '@r_Showerthoughts'


def send_post(submission, r2t):
    what, _, _ = get_url(submission)
    if what != 'text':
        False
    texts = [submission.title]
    punchline = submission.selftext.strip()
    if len(punchline) > 0:
        texts.append(punchline)
    main_text = '\n\n'.join(texts)
    link = submission.shortlink
    text = '{main}\n\n{link}'.format(
            main=main_text, link=link)
    r2t.send_text(text, disable_web_page_preview=True)
    return True
