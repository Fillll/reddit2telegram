#encoding:utf-8

import os

import utils.channels_stuff


def run_script(channel):
    os.system('python supplier.py --sub ' + channel.lower())


def med_fashioned_way():
    subreddit_name = input('Subreddit name: ')
    channel_name = input('Channel name: ')
    tags = input('#Tags #in #that #way: ')
    min_upvotes_limit = input('Minimum upvotes limit (default is None): ')
    min_upvotes_limit = None if min_upvotes_limit.strip() == '' else int(min_upvotes_limit.strip())
    submissions_ranking = input('Submissions ranking (default is hot): ')
    submissions_ranking = 'hot' if submissions_ranking.strip() == '' else submissions_ranking.strip()
    submissions_limit = input('Submissions limit (default is 100): ')
    submissions_limit = 100 if submissions_limit.strip() == '' else int(submissions_limit.strip())

    print('Submodule is created.')
    utils.channels_stuff.set_new_channel(channel_name, subreddit=subreddit_name,
                                                       tags=tags.lower(),
                                                       min_upvotes_limit=min_upvotes_limit,
                                                       submissions_ranking=submissions_ranking,
                                                       submissions_limit=submissions_limit
                                        )
    print(channel_name.lower())

    print('Run the bot for the first time.')
    run_script(channel_name)
    print('Done.')


if __name__ == '__main__':
    med_fashioned_way()
