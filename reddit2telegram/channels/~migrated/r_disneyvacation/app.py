#encoding:utf-8

from utils import get_url
from utils import SupplyResult

subreddit = 'disneyvacation'
t_channel = '@r_disneyvacation'


def send_post(submission, r2t):
	what, url = get_url(submission)
	title = submission.title
	link = submission.shortlink

	text = '{title}\n\n{link}\n{channel}'.format(
		title=title, link=link, channel=t_channel)
	if what == 'img':
		if r2t.dup_check_and_mark(url) is True:
			return SupplyResult.DO_NOT_WANT_THIS_SUBMISSION
		return r2t.send_gif_img(what, url, text)
	else:
	  return SupplyResult.DO_NOT_WANT_THIS_SUBMISSION
