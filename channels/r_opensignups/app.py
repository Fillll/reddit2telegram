#encoding:utf-8

from utils import get_url, weighted_random_subreddit


# Subreddit that will be a source of content
subreddit = weighted_random_subreddit({
    'opensignups': 1.0,
    # If we want get content from several subreddits
    # please provide here 'subreddit': probability
    # 'any_other_subreddit': 0.02
})
# Telegram channel with @reddit2telegram_bot as an admin
t_channel = '@r_opensignups'


def send_post(submission, r2t):
    what, url, ext = get_url(submission)

    # If this func returns:
    # False – it means that we will not send
    # this submission, let's move to the next.
    # True – everything is ok, we send the submission
    # None – we do not want to send anything this time,
    # let's just sleep.

    # Get all data from submission that we need
    title = submission.title
    link = submission.shortlink
    text = '{}\n{}'.format(title, link)

    if what == 'text':
        punchline = submission.selftext
        text = '{t}\n\n{p}\n\n{l}'.format(t=title, p=punchline, l=link)
        return r2t.send_text(text)
    elif what == 'other':
        base_url = submission.url
        text = '{t}\n{b}\n\n{l}'.format(t=title, b=base_url, l=link)
        return r2t.send_text(text)
    elif what == 'album':
        base_url = submission.url
        text = '{t}\n{b}\n\n{l}'.format(t=title, b=base_url, l=link)
        r2t.send_text(text)
        r2t.send_album(url)
        return True
    elif what in ('gif', 'img'):
        return r2t.send_gif_img(what, url, ext, text)
    else:
        return False
