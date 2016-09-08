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
            if chunk: # filter out keep-alive new chunks
                f.write(chunk)
                #f.flush() commented by recommendation from J.F.Sebastian
    return True


def was_before(url):
    client = pymongo.MongoClient()
    db = client['r_gifs']
    collection = db['history']
    result = collection.find_one({'url': url})
    if result is None:
        collection.insert_one({'url': url})
        return False
    else:
        return True


def do_work(config):
    r = praw.Reddit(user_agent=config['user_agent'])
    submissions = r.get_subreddit('gifs').get_hot(limit=100)
    for i in submissions:
        gif_url = get_url(i)
        if gif_url is None:
            continue
        if was_before(gif_url):
            continue
        caption = i.title
        link = i.short_link
        bot = telepot.Bot(config['telegram_token'])
        print('Gif url =', gif_url)
        text = '%s\n%s\n\nby @r_gifs' % (caption, link)

        # Download gif
        download_file(gif_url)
        # Telegram 50MB limitation
        if os.path.getsize('my.gif') > 50 * 1024 * 1024:
            continue
        f = open('my.gif', 'rb')
        bot.sendDocument('@r_gifs', f, caption=text)
        f.close()
        break


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='prod.yml')
    args = parser.parse_args()
    with open(args.config) as config_file:
        config = yaml.load(config_file.read())
    do_work(config)


if __name__ == '__main__':
    main()
