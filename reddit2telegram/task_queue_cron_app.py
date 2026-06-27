#encoding:utf-8
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)

import datetime
import csv
import os
import random

import pymongo
import yaml
from croniter import croniter

import task_queue


logger = logging.getLogger(__name__)


def read_own_cron(own_cron_filename, config, config_filename=None):
    with open(own_cron_filename) as tsv_file:
        tsv_reader = csv.DictReader(tsv_file, delimiter='\t')
        list_of_processes_to_start = list()
        for row in tsv_reader:
            now = datetime.datetime.now()
            cron = croniter(row['MASK'])
            prev_run = cron.get_prev(datetime.datetime)
            diff = now - prev_run
            diff_seconds = diff.total_seconds()
            if 0.0 <= diff_seconds and diff_seconds <= 59.9:
                submodule_name = row['submodule_name'].split('\t')[0]
                list_of_processes_to_start.append(submodule_name)
    random.shuffle(list_of_processes_to_start)
    db = pymongo.MongoClient(host=config['db']['host'])[config['db']['name']]
    task_args = []
    for submodule_name in list_of_processes_to_start:
        args = {'submodule_name': submodule_name}
        if config_filename is not None:
            args['config_filename'] = os.path.abspath(config_filename)
        else:
            args['config'] = config
        task_args.append(args)
    task_queue.submit_batch(db, task_queue.TASK_SUPPLY, task_args)


def main(config_filename):
    with open(config_filename) as config_file:
        config = yaml.safe_load(config_file.read())
        read_own_cron(config['cron_file'], config, config_filename=config_filename)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='configs/prod.yml')
    args = parser.parse_args()
    main(args.config)
