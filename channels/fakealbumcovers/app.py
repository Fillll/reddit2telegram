#encoding:utf-8

# Some utils can be useful.
from utils import get_url


# Write here subreddit name. Like this one for /r/jokes.
subreddit = 'fakealbumcovers'
# This is for your public telegram channel.
t_channel = '@fakealbumcovers'

separators = [" - ", " | ", "- ", "-", " by "]

def send_post(submission, r2t):
    what, url, ext = get_url(submission)
    
    fullTitle = submission.title
    link = submission.shortlink
    
    title = fullTitle
    artist = ""
    
    for sep in separators:
        if sep in fullTitle:
            if sep == " by ":
                artist = fullTitle[fullTitle.find(sep)+len(sep):]]
                title = fullTitle[:fullTitle.find(sep)
            else:
                artist = fullTitle[:fullTitle.find(sep)]
                title = fullTitle[fullTitle.find(sep)+len(sep):]
            break
    
    if artist != "":
        text = '{title}\n{artist}\n\n▶️{link}\n🎵{channel}'.format(
                title=title, artist=artist, link=link, channel=t_channel)
    else:
        text = '{title}\n\n▶️{link}\n🎵{channel}'.format(
                title=title, link=link, channel=t_channel)
        
       
    if what in ['text', 'other', 'album']:
        return False
    elif what == 'img':
        if r2t.dup_check_and_mark(url) is True:
            return False
        return r2t.send_gif_img(what, url, ext, text)
    else:
      return False
