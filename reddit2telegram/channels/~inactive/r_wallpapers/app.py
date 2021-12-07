#encoding:utf-8

subreddit = 'wallpaper'
t_channel = '@r_wallpapers'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
