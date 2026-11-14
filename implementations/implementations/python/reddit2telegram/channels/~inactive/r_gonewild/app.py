#encoding:utf-8

from utils import get_url, weighted_random_subreddit


# Subreddit that will be a source of content
subreddit = weighted_random_subreddit({
    'altgonewild': 0.0158730158730159,
    'analgw': 0.0158730158730159,
    'analgonewild': 0.0158730158730159,
    'asiansgonewild': 0.0158730158730159,
    'asiangw': 0.0158730158730159,
    'assholegonewild': 0.0158730158730159,
    'asstatic': 0.0158730158730159,
    'behindgonewild': 0.0158730158730159,
    'bbwgw': 0.0158730158730159,
    'bigboobsgonewild': 0.0158730158730159,
    'bigboobsgw': 0.0158730158730159,
    'bigbootiesgonewild': 0.0158730158730159,
    'boobsgonewild': 0.0158730158730159,
    'coffeegonewild': 0.0158730158730159,
    'couplesgonewildplus': 0.0158730158730159,
    'de_gonewild': 0.0158730158730159,
    'dirtypantiesgw': 0.0158730158730159,
    'dykesgonewild': 0.0158730158730159,
    'fmgonewild': 0.0158730158730159,
    'gifsgonewild': 0.0158730158730159,
    'gonewild18': 0.0158730158730159,
    'gonewild30plus': 0.0158730158730159,
    'gonewildalbums': 0.0158730158730159,
    'gonewildchubby': 0.0158730158730159,
    'gonewildcolor': 0.0158730158730159,
    'gonewildcurvy': 0.0158730158730159,
    'gonewildhairy': 0.0158730158730159,
    'gonewildhotties': 0.0158730158730159,
    'gonewild_italy': 0.0158730158730159,
    'gonewildmetal': 0.0158730158730159,
    'gonewildnz': 0.0158730158730159,
    'gonewildphotographers': 0.0158730158730159,
    'gonewildplus': 0.0158730158730159,
    'gonewildscrubs': 0.0158730158730159,
    'gonewildsmiles': 0.0158730158730159,
    'gonewild_gifs': 0.0158730158730159,
    'gonetoowild': 0.0158730158730159,
    'gwcouples': 0.0158730158730159,
    'gwcouples4ladies': 0.0158730158730159,
    'gwcumsluts': 0.0158730158730159,
    'gwnerdy': 0.0158730158730159,
    'highheelsgw': 0.0158730158730159,
    'hungrybuttsgw': 0.0158730158730159,
    'indiansgonewild': 0.0158730158730159,
    'labiagw': 0.0158730158730159,
    'latinasgw': 0.0158730158730159,
    'leggingsgonewild': 0.0158730158730159,
    'milfgw': 0.0158730158730159,
    'milfie': 0.0158730158730159,
    'mirl_gonewild': 0.0158730158730159,
    'pawgtastic': 0.0158730158730159,
    'petitegonewild': 0.0158730158730159,
    'ratemyasshole': 0.0158730158730159,
    'repressedgonewild': 0.0158730158730159,
    'sneakersgonewild': 0.0158730158730159,
    'sportygw': 0.0158730158730159,
    'swingersgw': 0.0158730158730159,
    'tallgonewild': 0.0158730158730159,
    'treesgonewild': 0.0158730158730159,
    'underweargw': 0.0158730158730159,
    'weddingsgonewild': 0.0158730158730159,
    'workoutgonewild': 0.0158730158730159,
    'workgonewild': 0.01587301587301
})
# Telegram channel with @reddit2telegram_bot as an admin
t_channel = '@r_gonewild'


def send_post(submission, r2t):
    what, url, ext = get_url(submission)

    # If this func returns:
    # False – it means that we will not send
    # this submission, let's move to the next.
    # True – everything is ok, we send the submission
    # None – we do not want to send anything this time,
    # let's just sleep.

    # Get all data from submission that we need
    title = submission.title
    link = submission.shortlink
    text = '{}\n{}'.format(title, link)

    if what == 'text':
        # If it is text submission, it is not really funny.
        # return r2t.send_text(submission.selftext)
        return False
    elif what == 'other':
        # Also we are not interesting in any other content.
        return False
    elif what == 'album':
        # It is ok if it is an album.
        base_url = submission.url
        text = '{}\n{}\n\n{}'.format(title, base_url, link)
        r2t.send_text(text)
        r2t.send_album(url)
        return True
    elif what in ('gif', 'img'):
        # Also it is ok if it is gif or any kind of image.

        # Check if content has already appeared in
        # out telegram channel.
        if r2t.dup_check_and_mark(url) is True:
            return False
        return r2t.send_gif_img(what, url, ext, text)
    else:
        return False
