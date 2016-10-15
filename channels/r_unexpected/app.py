# encoding: utf-8

from utils import get_url
import logging
from pytgbot.bot import Bot
from pytgbot.exceptions import TgApiException

logger = logging.getLogger(__name__)

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
    logger.info("{channel} Posting {gif_url}:\n{text}".format(channel=t_channel, gif_url=gif_url, text=text))
    try:
        bot.send_document(t_channel, document=gif_url, caption=text)
    except TgApiException:
        from pytgbot.api_types.sendable.files import InputFileFromURL
        bot.send_document(t_channel, document=InputFileFromURL(gif_url), caption=text)
    return True
