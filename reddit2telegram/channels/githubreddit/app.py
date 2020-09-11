#encoding:utf-8

from utils import weighted_random_subreddit


subreddit = weighted_random_subreddit({
	'GitHub': 1,
	'coolgithubProjects': 1
})
t_channel = '@GitHubReddit'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
