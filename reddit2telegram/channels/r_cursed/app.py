#encoding:utf-8

subreddit = 'cursedimages+cursedcomments+cursedmemes+cursed_images+cursedguns+hmmm'
t_channel = '@r_cursed'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
