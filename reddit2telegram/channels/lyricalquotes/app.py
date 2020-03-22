#encoding:utf-8

subreddit = 'quotes'
t_channel = '@lyricalquotes'


def send_post(submission, r2t):
    return r2t.send_simple(submission, disable_web_page_preview=True)
