#encoding:utf-8

subreddit = 'terriblefacebookmemes'
t_channel = '@TerribleFacebookMemes'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
