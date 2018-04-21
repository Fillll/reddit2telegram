# encoding: utf-8

import logging
import yaml
import os

from utils import get_url
from utils import SupplyResult
from yandex_translate import YandexTranslate


subreddit = 'unexpected'
t_channel = '@r_unexpected'
yandex_key = yaml.load(open(os.path.join('configs','ya.translate.yml')))['translate_api_key']  # to be filled by conf
NSFW_EMOJI = u'\U0001F51E'


def translate_yandex(text, src="auto", dst="en"):
    if src != "auto":
        lang = "{src}-{dst}".format(src=src, dst=dst)
    else:
        lang = dst
    langdex = YandexTranslate(yandex_key)
    result = langdex.translate(text, lang)
    assert result['code'] == 200
    return result['text'][0]


def send_post(submission, r2t):
    what, url, ext = get_url(submission)

    title = submission.title
    link = submission.shortlink

    main_text = [title]
    # Translation magic
    try:
        translation = translate_yandex(title)
        if translation.lower() == title.lower():
            pass
        else:
            main_text.append(translation)
    except Exception as e:
        logging.warning('Ya.Translate: {}.'.format(e))
    # End of translation mahic
    main_text = '\n\n'.join(main_text)
    text = '{text}\n{link}\n\nby {channel}'.format(text=main_text, link=link, channel=t_channel)

    if submission.over_18:
        url = submission.url
        text = '{emoji}NSFW\n{url}\n{title}\n\n{link}\n\nby {channel}'.format(
            emoji=NSFW_EMOJI, url=url, title=title, link=link, channel=t_channel
        )
        return r2t.send_text(text, disable_web_page_preview=True)

    if r2t.dup_check_and_mark(url) is True:
        return SupplyResult.DO_NOT_WANT_THIS_SUBMISSION

    return r2t.send_gif_img(what, url, ext, text)
