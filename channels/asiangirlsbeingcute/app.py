#encoding:utf-8

# import os

# from utils import get_url
# from urllib.parse import urlparse

subreddit = 'asiangirlsbeingcute'
t_channel = '@asiangirlsbeingcute'


# Commented a lot, since mp4 from streamable mostly not works.


# def get_gif(submission):
#     url = submission.url
#     # TODO: Better url validation
#     if url.endswith('.gif'):
#         return 'gif', url
#     elif url.endswith('.gifv'):
#         return 'gif', url[0:-1]
#     elif urlparse(url).netloc == 'www.reddit.com':
#         return 'text', None
#     elif urlparse(url).netloc == 'gfycat.com':
#         gifurl = 'https://thumbs.gfycat.com' + urlparse(url).path + '-size_restricted.gif'
#         return 'gif', gifurl
#     elif urlparse(url).netloc == 'streamable.com':
#         mp4Url = 'https://cdn.streamable.com/video/mp4' + urlparse(url).path + '.mp4'
#         return 'mp4', mp4Url
#     else:
#         return 'other', url


def send_post(submission, r2t):
    # what, gif_url = get_gif(submission)
    # if what not in ('gif', 'mp4'):
    #     return False
    return r2t.send_simple(submission, text=False, other=False)
    # # Determine file
    # if what == 'gif':
    #     t_file = 'asiangirlsbeingcute.gif'
    #     #Download file    
    #     if not download_file(gif_url, t_file):
    #         return False
    #     # Telegram will not autoplay big gifs
    #     if os.path.getsize(t_file) > telegram_autoplay_limit:
    #         return False
    #     text = '{}\n{}'.format(title, link)
    #     f = open(t_file, 'rb')
    #     bot.sendDocument(t_channel, f, caption=text)
    #     f.close()
    #     return True
    # elif what == 'mp4':
    #     url = gif_url
    #     text = '{}\n{}\n\n{}'.format(title, url, link)
    #     bot.sendMessage(t_channel, text)
    #     return True
    # else:
    #     return False
