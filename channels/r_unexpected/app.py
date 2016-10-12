#encoding:utf-8

import os

from utils import get_url

from pytgbot.bot import Bot


subreddit = 'unexpected'
t_channel = '@r_unexpected'

NSFW_emoji = u"\U0001F51E"

def send_post(submission, bot):
    bot = Bot(bot._token)
    what, gif_url, _ = get_url(submission)
    if what != 'gif':
        return False

    title = submission.title
    link = submission.short_link

    if submission.over_18:
        url = submission.url
        text = '{emoji}NSFW\n{url}\n{title}\n\n{link}\n\nby {channel}'.format(
            emoji=NSFW_emoji, url=url, title=title, link=link, channel=t_channel
        )
        bot.send_message(t_channel, text, disable_web_page_preview=True)
        return True

    text = '{title}\n{link}\n\nby {channel}'.format(title=title, link=link, channel=t_channel)

    bot.send_document(t_channel, document=gif_url, caption=text)
    return True
#encoding:utf-8

import os

from utils import get_url

from pytgbot.bot import Bot


subreddit = 'unexpected'
t_channel = '@r_unexpected'

NSFW_emoji = u"\U0001F51E"

def send_post(submission, bot):
    bot = Bot(bot._token)
    what, gif_url, _ = get_url(submission)
    if what != 'gif':
        return False

    title = submission.title
    link = submission.short_link

    if submission.over_18:
        url = submission.url
        text = '{emoji}NSFW\n{url}\n{title}\n\n{link}\n\nby {channel}'.format(
            emoji=NSFW_emoji, url=url, title=title, link=link, channel=t_channel
        )
        bot.send_message(t_channel, text, disable_web_page_preview=True)
        return True

    text = '{title}\n{link}\n\nby {channel}'.format(title=title, link=link, channel=t_channel)

    bot.send_document(t_channel, document=gif_url, caption=text)
    return True
