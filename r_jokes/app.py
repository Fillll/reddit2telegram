#encoding:utf-8

import argparse

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


def do_work(subreddit, t_channel, config):
    r = praw.Reddit(user_agent=config['user_agent'])
    submissions = r.get_subreddit(subreddit).get_hot(limit=100)
    for i in submissions:
        link = i.short_link
        if was_before(link, t_channel, config):
            continue
        title = i.title
        punchline = i.selftext
        text = '%s\n\n%s\n\n%s' % (title, punchline, link)
        bot = telepot.Bot(config['telegram_token'])
        bot.sendMessage(t_channel, text)
        break


def main(subreddit, t_channel):
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='prod.yml')
    args = parser.parse_args()
    with open(args.config) as config_file:
        config = yaml.load(config_file.read())
    do_work(subreddit, t_channel, config)


if __name__ == '__main__':
    main('jokes', '@r_jokes')
