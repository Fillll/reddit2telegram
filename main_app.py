#encoding:utf-8

import argparse
import importlib
from datetime import datetime
import logging

import yaml
import praw
import telepot
import pymongo
from sentry import report_error

import utils


logger = logging.getLogger(__name__)


def was_before(url, channel, config):
    collection = pymongo.MongoClient(host=config['db_host'])[config['db']]['urls']
    result = collection.find_one({'channel': channel.lower(), 'url': url})
    if result is None:
        return False
    else:
        return True


def mark_as_was_before(url, channel, config):
    collection = pymongo.MongoClient(host=config['db_host'])[config['db']]['urls']
    collection.insert_one({
        'url': url,
        'ts': datetime.utcnow(),
        'channel': channel.lower()
    })


def store_stats(channel, bot, config):
    collection = pymongo.MongoClient(host=config['db_host'])[config['db']]['stats']
    stat = {
        'channel': channel.lower(),
        'ts': datetime.utcnow(),
        'members_cnt': bot.getChatMembersCount(channel)
    }
    collection.insert_one(stat)


@report_error
def supply(subreddit, config):
    submodule = importlib.import_module('channels.{}.app'.format(subreddit))
    reddit = praw.Reddit(user_agent=config['user_agent'])
    submissions = reddit.get_subreddit(submodule.subreddit).get_hot(limit=100)
    bot = telepot.Bot(config['telegram_token'])
    store_stats(submodule.t_channel, bot, config)
    r2t = utils.Reddit2TelegramSender(submodule.t_channel, bot)
    success = False
    for submission in submissions:
        link = submission.short_link
        if was_before(link, submodule.t_channel, config):
            continue
        success = submodule.send_post(submission, r2t)
        if success is True:
            # Every thing is ok, post was sent
            mark_as_was_before(link, submodule.t_channel, config)
            break
        elif success is False:
            # Do not want to send this post
            mark_as_was_before(link, submodule.t_channel, config)
            continue
        else:
            break
    if not success:
        logger.info('Nothing to post from {sub} to {channel}.'.format(
                    sub=submodule.subreddit, channel=submodule.t_channel))


def main(config_filename, sub):
    with open(config_filename) as config_file:
        config = yaml.load(config_file.read())
    supply(sub, config)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='prod.yml')
    parser.add_argument('--sub')
    args = parser.parse_args()
    main(args.config, args.sub)
