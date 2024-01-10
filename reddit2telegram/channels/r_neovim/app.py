#encoding:utf-8

subreddit = 'neovim'
t_channel = '@r_neovim'


def send_post(submission, r2t):
    return r2t.send_simple(submission,
        # Submission should have at least min_upvotes_limit upvotes.
        min_upvotes_limit=10,
        # If you do not want text submissions, just pass False.
        text=True,
        # If you want gifs, just pass True or text you want under gif.
        gif=True,
        # If you want videos, just pass True or text you want under gif.
        video=True,
        # If you want images, just pass True or text you want under image.
        img=True,
        # If you want Imgur albums, just pass True or text you want under albums.
        album=True,
        # If you want Reddit galleries, just pass True or text you want under albums.
        gallery=True,
        # If you do not want other submissions, just pass False.
        other=False
    )
