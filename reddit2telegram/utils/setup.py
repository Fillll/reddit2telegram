#encoding:utf-8

import os
import importlib

import pymongo
import yaml

import tech


def get_config(config_filename=None):
    if config_filename is None:
        config_filename = os.path.join('configs', 'prod.yml')
    with open(config_filename) as config_file:
        return yaml.load(config_file.read())


def create_view_with_first_dates(config_filename=None):
    print('FIRST DATES BEGIN.')
    VIEW_NAME = 'view_with_first_dates'
    config = get_config(config_filename)
    db = pymongo.MongoClient(host=config['db']['host'])[config['db']['name']]
    if VIEW_NAME not in db.collection_names():
        db.command('create', VIEW_NAME,
            viewOn='urls', 
            pipeline=[
                {
                    '$group':
                        {
                            '_id': '$channel',
                            'first_date':
                                {
                                    '$min': '$ts'
                                }
                        }
                }
            ]
        )
    print('FIRST DATES END.')


def ensure_index(config_filename=None):
    print('ENSURE INDEX BEGIN.')
    config = get_config(config_filename)
    db = pymongo.MongoClient(host=config['db']['host'])[config['db']['name']]
    stats = db['stats']
    stats.ensure_index([('channel', pymongo.ASCENDING), ('ts', pymongo.ASCENDING)])
    urls = db['urls']
    urls.ensure_index([('channel', pymongo.ASCENDING), ('url', pymongo.ASCENDING)])
    contents = db['contents']
    contents.ensure_index([('channel', pymongo.ASCENDING), ('md5_sum', pymongo.ASCENDING)])
    errors = db['errors']
    errors.ensure_index([('channel', pymongo.ASCENDING), ('url', pymongo.ASCENDING)])
    settings = db['settings']
    settings.ensure_index([('setting', pymongo.ASCENDING)])
    print('ENSURE INDEX END.')


def get_all_public_submodules_and_channels_sroted(config_filename=None):
    config = get_config(config_filename)
    db = pymongo.MongoClient(host=config['db']['host'])[config['db']['name']]
    dates = db['dates']
    submodules_and_dates = dict()
    all_submodules = tech.get_all_public_submodules(config_filename)
    for submodule in all_submodules:
        imported = importlib.import_module('.channels.{}.app'.format(submodule))
        channel = imported.t_channel
        first_date_result = dates.find_one({'_id': channel.lower()})
        if first_date_result is None:
            continue
        submodules_and_dates[(submodule, channel)] = first_date_result['first_date']
    for item in sorted(submodules_and_dates.keys(), key=submodules_and_dates.get, reverse=0):
        print('{submodule}\t{channel}\t{date}'.format(submodule=item[0][0], channel=item[0][1], date=item[1]))


def main():
    ensure_index()
    create_view_with_first_dates()
    get_all_public_submodules_and_channels_sroted()


if __name__ == '__main__':
    main()
