# encoding: utf-8

from utils import get_url


subreddit = 'unexpected'
t_channel = '@r_unexpected'
yandex_key = None  # to be filled by conf

NSFW_EMOJI = u'\U0001F51E'

def translate_yandex(text, src="auto", dst="en"):
    if src != "auto":
        lang = "{src}-{dst}".format(src=src, dst=dst)
    else:
        lang = dst
    # end if
    from yandex_translate import YandexTranslate
    langdex = YandexTranslate(yandex_key)
    result = DictObject.objectify(langdex.translate(text, lang))
    assert result['code'] == 200
    return result['text'][0]
# end try



def send_post(submission, r2t):
    what, url, ext = get_url(submission)

    title = submission.title
    link = submission.shortlink

    try:
        translation = translate_yandex(title)
        if translation.lower() == title.lower():
            raise ValueError("lol, k")
        # end if
        text = '{title}\n{translation}\n{link}\n\nby {channel}'.format(title=title, translation=translation, link=link, channel=t_channel)
    except:    
        text = '{title}\n{link}\n\nby {channel}'.format(title=title, link=link, channel=t_channel)
    # end try

    if submission.over_18:
        url = submission.url
        text = '{emoji}NSFW\n{url}\n{title}\n\n{link}\n\nby {channel}'.format(
            emoji=NSFW_EMOJI, url=url, title=title, link=link, channel=t_channel
        )
        return r2t.send_text(text, disable_web_page_preview=True)

    if r2t.dup_check_and_mark(url) is True:
        return False

    return r2t.send_gif_img(what, url, ext, text)
