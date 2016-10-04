#encoding:utf-8

from utils import (get_url, download_file, telegram_autoplay_limit,
                    just_send_an_album)


subreddit = 'behindthegifs'
t_channel = '@r_behindthegifs'


def send_post(submission, bot):
    what, story = get_url(submission)
    if what != 'album':
        return False

    title = submission.title
    url = submission.url
    link = submission.short_link
    text = '{}\n{}\n\n{}'.format(title, url, link)
    bot.sendMessage(t_channel, text)

    just_send_an_album(t_channel, story, bot)
    return True
