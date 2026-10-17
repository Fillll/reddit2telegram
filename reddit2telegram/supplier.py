#encoding:utf-8

import logging

import yaml
import praw
from praw.models import ListingGenerator
import requests

import utils
from utils.http_resources import session as http_session
from reporting_stuff import report_error
from utils.tech import long_sleep, short_sleep, no_chance_to_post_due_to_errors_cnt


def _bound_listing_page_size(submissions):
    if isinstance(submissions, ListingGenerator):
        # PRAW's limit caps the total candidates, while this request parameter
        # caps each retained page. Pagination still examines the full limit.
        submissions.params['limit'] = min(submissions.limit or 25, 25)
    return submissions


def submissions_safe(submissions):
    # Because reddit start banning for too much API calls.
    for i in range(10):
        try:
            yield next(submissions)
        except StopIteration:
            return
        except Exception as e:
            long_sleep(2.818281828 * 3.14159 / 2)


@utils.media_job()
def send_to_channel_from_subreddit(how_to_post, channel_to_post, subreddit, submissions_ranking, submissions_limit, config, **kwargs):
    # PRAW does not close its HTTP session on context-manager exit.
    with http_session() as reddit_http:
        reddit = praw.Reddit(
            user_agent=config['reddit']['user_agent'],
            client_id=config['reddit']['client_id'],
            client_secret=config['reddit']['client_secret'],
            username=config['reddit']['username'],
            password=config['reddit']['password'],
            requestor_kwargs={'timeout': utils.REDDIT_TIMEOUT, 'session': reddit_http}
        )
        if submissions_ranking == 'top':
            submissions = reddit.subreddit(subreddit).top(limit=submissions_limit)
        elif submissions_ranking == 'hot':
            submissions = reddit.subreddit(subreddit).hot(limit=submissions_limit)
        elif submissions_ranking == 'new':
            submissions = reddit.subreddit(subreddit).new(limit=submissions_limit)
        else:
            logging.error('Unknown submissions_ranking. {}'.format(submissions_ranking))
        _bound_listing_page_size(submissions)
        with utils.Reddit2TelegramSender(channel_to_post, config) as r2t:
            success = False
            for submission in submissions_safe(submissions):
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
            return success


@report_error
def supply(submodule_name, config, is_test=False):
    if not is_test:
        long_sleep(0.2)
    submodule = utils.channels_stuff.import_submodule(submodule_name)
    if not getattr(submodule, 'requires_submission', True):
        channel = '@r_channels_test' if is_test else submodule.t_channel
        with utils.Reddit2TelegramSender(channel, config) as r2t:
            return submodule.send_post(None, r2t)
    submissions_ranking_stated = getattr(submodule, 'submissions_ranking', None)
    if submissions_ranking_stated not in ['hot', 'new', 'top']:
        submissions_ranking = 'hot'
    else:
        submissions_ranking = submissions_ranking_stated
    submissions_limit = getattr(submodule, 'submissions_limit', 100)
    channel_to_post = submodule.t_channel if not is_test else '@r_channels_test'
    with utils.Reddit2TelegramSender(channel_to_post, config) as r2t:
        if no_chance_to_post_due_to_errors_cnt(r2t, channel_to_post):
            return
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
    utils.clean_after_module(channel_to_post)


def main(config_filename, sub, is_test=False):
    with open(config_filename) as config_file:
        config = yaml.safe_load(config_file.read())
        if not is_test:
            supply(sub, config, is_test)
        else:
            for i in range(100):
                print('i =', i, '>')
                supply(sub, config, is_test)
                short_sleep(0.1)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='configs/prod.yml')
    parser.add_argument('--test', action='store_true')
    parser.add_argument('--sub')
    args = parser.parse_args()
    main(args.config, args.sub, args.test)
