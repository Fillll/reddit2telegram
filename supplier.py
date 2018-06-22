#encoding:utf-8

import importlib
import logging

import yaml
import praw

import utils
from reporting_stuff import report_error
from praw.models import MoreComments

@report_error
def supply(submodule_name, config):
    submodule = importlib.import_module('channels.{}.app'.format(submodule_name))
    reddit = praw.Reddit(user_agent=config['reddit']['user_agent'],
                        client_id=config['reddit']['client_id'],
                        client_secret=config['reddit']['client_secret'])
    submissions = reddit.subreddit(submodule.subreddit).hot(limit=100)
    comments = reddit.subreddit(submodule.subreddit).hot(limit=100).comments(limit=25)
    r2t = utils.Reddit2TelegramSender(submodule.t_channel, config)
    success = False


    if(hasattr(submodule, "send_comment")):
        for top_level_comment in comments:
            if isinstance(top_level_comment, MoreComments):
                continue
            link = top_level_comment.shortlink
            if r2t.was_before(link):
                continue
            success = submodule.send_comment(top_level_comment, r2t)
            if success == utils.SupplyResult.SUCCESSFULLY:
                # Every thing is ok, comment was sent
                r2t.mark_as_was_before(link)
                break
            elif success == utils.SupplyResult.DO_NOT_WANT_THIS_SUBMISSION:
                # Do not want to send this comment
                r2t.mark_as_was_before(link)
                continue
            elif success == utils.SupplyResult.SKIP_FOR_NOW:
                # Do not want to send now
                continue
            elif success == utils.SupplyResult.STOP_THIS_SUPPLY:
                # If None — do not want to send anything this time
                break
            else:
                logging.error('Unknown SupplyResult. {}'.format(success))
        if success is False:
            logging.info('Nothing to post from {sub} to {channel}.'.format(
                        sub=submodule.subreddit, channel=submodule.t_channel))

    success = False
    for submission in submissions:
        link = submission.shortlink
        if r2t.was_before(link):
            continue
        success = submodule.send_post(submission, r2t)
        if success == utils.SupplyResult.SUCCESSFULLY:
            # Every thing is ok, post was sent
            r2t.mark_as_was_before(link)
            break
        elif success == utils.SupplyResult.DO_NOT_WANT_THIS_SUBMISSION:
            # Do not want to send this post
            r2t.mark_as_was_before(link)
            continue
        elif success == utils.SupplyResult.SKIP_FOR_NOW:
            # Do not want to send now
            continue
        elif success == utils.SupplyResult.STOP_THIS_SUPPLY:
            # If None — do not want to send anything this time
            break
        else:
            logging.error('Unknown SupplyResult. {}'.format(success))
    if success is False:
        logging.info('Nothing to post from {sub} to {channel}.'.format(
                    sub=submodule.subreddit, channel=submodule.t_channel))


def main(config_filename, sub):
    with open(config_filename) as config_file:
        config = yaml.load(config_file.read())
        supply(sub, config)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='configs/prod.yml')
    parser.add_argument('--sub')
    args = parser.parse_args()
    main(args.config, args.sub)
