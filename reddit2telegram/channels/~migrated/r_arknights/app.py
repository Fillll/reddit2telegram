subreddit = 'arknights'
t_channel = '@r_arknights'


def send_post(submission, r2t):
    return r2t.send_simple(
        submission,
        text=True,
        gif=True,
        video=True,
        img=True,
        album=True,
        other=True,
    )