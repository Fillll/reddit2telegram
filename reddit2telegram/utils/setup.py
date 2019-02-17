#encoding:utf-8

import os
import csv

import pymongo
import yaml


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


def set_tags():
    with open(os.path.join('utils', 'tag_list.tsv')) as master_tags_file:
        for line in csv.DictReader(master_tags_file, fieldnames=('submodule', 'channel', 'tags'), delimiter='\t'):
            if line['submodule'].strip() == 'SUBMODULE':
                continue
            with open(os.path.join('channels', line['submodule'].strip(), 'tags.txt'), 'w') as local_tags_file:
                local_tags_file.write(line['tags'].strip())


def main():
    ensure_index()
    create_view_with_first_dates()
    set_tags()


if __name__ == '__main__':
    main()
