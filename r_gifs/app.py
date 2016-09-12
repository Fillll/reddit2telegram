#encoding:utf-8

import argparse
import os

import yaml
import praw
import telepot
import pymongo
import requests


def get_url(submission):
    url = submission.url
    # TODO: Better url validation
    if url.endswith('.gif'):
        return url
    elif url.endswith('.gifv'):
        return url[0:-1]
    else:
        return None


def download_file(url):
    # http://stackoverflow.com/questions/16694907/how-to-download-large-file-in-python-with-requests-py
    # NOTE the stream=True parameter
    r = requests.get(url, stream=True)
    with open('my.gif', 'wb') as f:
        for chunk in r.iter_content(chunk_size=1024): 
            if chunk:  # filter out keep-alive new chunks
                f.write(chunk)
                #f.flush() commented by recommendation from J.F.Sebastian
    return True


def was_before(url, channel, config):
    collection = pymongo.MongoClient()[config['db']][channel[1:]]
    result = collection.find_one({'url': url})
    if result is None:
        collection.insert_one({'url': url})
        return False
    else:
        return True


def supply(subreddit, t_channel, config):
    r = praw.Reddit(user_agent=config['user_agent'])
    submissions = r.get_subreddit(subreddit).get_hot(limit=100)
    for i in submissions:
        gif_url = get_url(i)
        if gif_url is None:
            continue
        if was_before(gif_url, t_channel, config):
            continue
        title = i.title
        link = i.short_link
        caption = '%s\n%s\n\nby @r_gifs' % (title, link)
        # Download gif
        download_file(gif_url)
        # Telegram 50MB limitation
        if os.path.getsize('my.gif') > 12 * 1024 * 1024:
            continue
        f = open('my.gif', 'rb')
        bot = telepot.Bot(config['telegram_token'])
        bot.sendDocument(t_channel, f, caption=caption)
        f.close()
        break


def main(subreddit, t_channel):
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='prod.yml')
    args = parser.parse_args()
    with open(args.config) as config_file:
        config = yaml.load(config_file.read())
    supply(subreddit, t_channel, config)


if __name__ == '__main__':
    main('gifs', '@r_gifs')
