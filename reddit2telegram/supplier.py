#encoding:utf-8

import importlib
import logging
import random
import time

import yaml
import praw

import utils
from reporting_stuff import report_error


def send_to_channel_from_subreddit(how_to_post, channel_to_post, subreddit, submissions_ranking, submissions_limit, config, **kwargs):
    reddit = praw.Reddit(
        user_agent=config['reddit']['user_agent'],
        client_id=config['reddit']['client_id'],
        client_secret=config['reddit']['client_secret'],
        username=config['reddit']['username'],
        password=config['reddit']['password']
    )
    if submissions_ranking == 'top':
        submissions = reddit.subreddit(subreddit).top(limit=submissions_limit)
    elif submissions_ranking == 'hot':
        submissions = reddit.subreddit(subreddit).hot(limit=submissions_limit)
    elif submissions_ranking == 'new':
        submissions = reddit.subreddit(subreddit).new(limit=submissions_limit)
    else:
        logging.error('Unknown submissions_ranking. {}'.format(submissions_ranking))
    r2t = utils.Reddit2TelegramSender(channel_to_post, config)
    success = False
    for submission in submissions:
        link = submission.shortlink
        if r2t.was_before(link):
            continue
        if r2t.too_much_errors(link):
            continue
        if kwargs.get('extra_args', False):
            success = how_to_post(submission, r2t, **kwargs)
        else:
            success = how_to_post(submission, r2t)
        if success == utils.SupplyResult.SUCCESSFULLY:
            # Every thing is ok, post was sent
            r2t.mark_as_was_before(link, sent=True)
            break
        elif success == utils.SupplyResult.DO_NOT_WANT_THIS_SUBMISSION:
            # Do not want to send this post
            r2t.mark_as_was_before(link, sent=False)
            continue
        elif success == utils.SupplyResult.SKIP_FOR_NOW:
            # Do not want to send now
            continue
        elif success == utils.SupplyResult.STOP_THIS_SUPPLY:
            # If None — do not want to send anything this time
            break
        else:
            logging.error('Unknown SupplyResult. {}'.format(success))


@report_error
def supply(submodule_name, config, is_test=False):
    if not is_test:
        time.sleep(random.randrange(0, 40))
    submodule = importlib.import_module('channels.{}.app'.format(submodule_name))
    submissions_ranking_stated = getattr(submodule, 'submissions_ranking', None)
    if submissions_ranking_stated not in ['hot', 'new', 'top']:
        submissions_ranking = 'hot'
    else:
        submissions_ranking = submissions_ranking_stated
    submissions_limit = getattr(submodule, 'submissions_limit', 100)
    channel_to_post = submodule.t_channel if not is_test else '@r_channels_test'
    success = send_to_channel_from_subreddit(how_to_post=submodule.send_post,
        channel_to_post=channel_to_post,
        subreddit=submodule.subreddit,
        submissions_ranking=submissions_ranking,
        submissions_limit=submissions_limit,
        config=config,
        extra_args=False
    )
    if success is False:
        logging.info('Nothing to post from {sub} to {channel}.'.format(
                    sub=submodule.subreddit, channel=submodule.t_channel))
        if submissions_ranking_stated is None:
            success = send_to_channel_from_subreddit(how_to_post=submodule.send_post,
                channel_to_post=channel_to_post,
                subreddit=submodule.subreddit,
                submissions_ranking='new',
                submissions_limit=submissions_limit,
                config=config,
                extra_args=False
            )
            if success is False:
                success = send_to_channel_from_subreddit(how_to_post=submodule.send_post,
                    channel_to_post=channel_to_post,
                    subreddit=submodule.subreddit,
                    submissions_ranking='top',
                    submissions_limit=submissions_limit,
                    config=config,
                    extra_args=False
                )


def main(config_filename, sub, is_test=False):
    with open(config_filename) as config_file:
        config = yaml.safe_load(config_file.read())
        supply(sub, config, is_test)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='configs/prod.yml')
    parser.add_argument('--test', action='store_true')
    parser.add_argument('--sub')
    args = parser.parse_args()
    main(args.config, args.sub, args.test)
