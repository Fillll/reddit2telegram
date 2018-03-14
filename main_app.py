#encoding:utf-8

import importlib

import yaml
import praw

import utils
from reporting_stuff import report_error


@report_error
def supply(submodule_name, config):
    submodule = importlib.import_module('channels.{}.app'.format(submodule_name))
    reddit = praw.Reddit(user_agent=config['reddit']['user_agent'],
                        client_id=config['reddit']['client_id'],
                        client_secret=config['reddit']['client_secret'])
    submissions = reddit.subreddit(submodule.subreddit).hot(limit=100)
    r2t = utils.Reddit2TelegramSender(submodule.t_channel, config)
    success = False
    for submission in submissions:
        link = submission.shortlink
        if r2t.was_before(link):
            continue
        success = submodule.send_post(submission, r2t)
        if success is True:
            # Every thing is ok, post was sent
            r2t.mark_as_was_before(link)
            break
        elif success is False:
            # Do not want to send this post
            r2t.mark_as_was_before(link)
            continue
        else:
            # If None — do not want to send anything this time
            break
    if success is False:
        logger.info('Nothing to post from {sub} to {channel}.'.format(
                    sub=submodule.subreddit, channel=submodule.t_channel))


def main(config_filename, sub):
    with open(config_filename) as config_file:
        config = yaml.load(config_file.read())
    supply(sub, config)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='prod.yml')
    parser.add_argument('--sub')
    args = parser.parse_args()
    main(args.config, args.sub)
