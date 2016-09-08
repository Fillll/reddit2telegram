#encoding:utf-8

import argparse
import urllib
import os

import yaml
import praw
import telepot


def get_url(submission):
    url = submission.url
    # TODO: Better url validation
    if url.endswith('.gif'):
        return url
    elif url.endswith('.gifv'):
        return url[0:-1]
    else:
        return None


def do_work(config):
    r = praw.Reddit(user_agent=config['user_agent'])
    submissions = r.get_subreddit('gifs').get_hot(limit=10)
    for i in submissions:
        # TODO: check if it was sent before
        gif_url = get_url(i)
        if gif_url is None:
            continue
        caption = i.title
        link = i.short_link
        bot = telepot.Bot(config['telegram_token'])
        print('Gif url =', gif_url)
        text = '%s\n%s\n\nby @r_gifs' % (caption, link)

        # Download and send
        urllib.request.urlretrieve(gif_url, 'my.gif')
        if os.path.getsize('my.gif') > 50 * 1024 * 1024:
            continue
        f = open('my.gif', 'rb')
        bot.sendDocument('@r_gifs_test', f, caption=text)
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
