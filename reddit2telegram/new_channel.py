#encoding:utf-8

import os

import utils.channels_stuff


def run_script(channel):
    os.system('python supplier.py --sub ' + channel.lower())


def med_fashioned_way():
    subreddit_name = input('Subreddit name: ')
    channel_name = input('Channel name: ')
    tags = input('#Tags #in #that #way: ')

    print('Submodule is created.')
    utils.channels_stuff.set_new_channel(channel_name, subreddit=subreddit_name, tags=tags.lower())
    print(channel_name.lower())

    print('Run the bot for the first time.')
    run_script(channel_name)
    print('Done.')


if __name__ == '__main__':
    med_fashioned_way()
