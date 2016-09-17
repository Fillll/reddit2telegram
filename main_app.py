#encoding:utf-8

import argparse
import importlib

import yaml
import praw
import telepot
import pymongo


def was_before(url, channel, config):
    collection = pymongo.MongoClient()[config['db']][channel[1:]]
    result = collection.find_one({'url': url})
    if result is None:
        collection.insert_one({'url': url})
        return False
    else:
        return True


def supply(subreddit, config):
    submodule = importlib.import_module('channels.r_{}.app'.format(subreddit))
    reddit = praw.Reddit(user_agent=config['user_agent'])
    submissions = reddit.get_subreddit(submodule.subreddit).get_hot(limit=100)
    for submission in submissions:
        link = submission.short_link
        if was_before(link, submodule.t_channel, config):
            continue
        bot = telepot.Bot(config['telegram_token'])
        success = submodule.send_post(submission, bot)
        if success:
            break
        else:
            continue


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='prod.yml')
    parser.add_argument('--sub')
    args = parser.parse_args()
    with open(args.config) as config_file:
        config = yaml.load(config_file.read())
    supply(args.sub, config)


if __name__ == '__main__':
    main()
