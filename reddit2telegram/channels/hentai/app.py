#encoding:utf-8

from utils import weighted_random_subreddit({
    'hentai':0.1
    'hentai_gifs': 0.1
    'ecchi': 0.1
    'ecchigifs': 0.1
    'AnimeMILFS': 0.1
    'HentaiSource': 0.1
    'HentaiAnime': 0.1
    'UncensoredHentai': 0.1
    'NSFWAnimeWallpaper': 0.1
})
t_channel = '@H3nTA1I'

def send_post(submission, r2t):
    return r2t.send_simple(submission,
        text=False,
        gif=True,
        img=True,
        album=True,
        other=False
    )