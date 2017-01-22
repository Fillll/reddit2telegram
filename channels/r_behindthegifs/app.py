#encoding:utf-8

from utils import get_url


subreddit = 'behindthegifs'
t_channel = '@r_behindthegifs'


def send_post(submission, r2t):
    what, story, _ = get_url(submission)
    if what != 'album':
        return False

    title = submission.title
    url = submission.url
    link = submission.shortlink
    text = '{}\n{}\n\n{}'.format(title, url, link)
    r2t.send_text(text)
    r2t.send_album(story)
    return True
