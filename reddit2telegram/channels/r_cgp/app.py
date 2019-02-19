#encoding:utf-8

from utils import weighted_random_subreddit


subreddit = weighted_random_subreddit({
    'CoolGithubProjects': 1,
    'coolcstechtalks': 1
})
t_channel = '@r_CoolGithubProjects'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
