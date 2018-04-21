#encoding:utf-8

import datetime
import csv
import logging

import yaml
from croniter import croniter

from supplier import supply


logger = logging.getLogger(__name__)


def read_own_cron(own_cron_filename, config):
    with open(own_cron_filename) as tsv_file:
        tsv_reader = csv.DictReader(tsv_file, delimiter='\t')
        for row in tsv_reader:
            now = datetime.datetime.now()
            cron = croniter(row['MASK'])
            # prev_run = cron.get_current(datetime.datetime)
            prev_run = cron.get_prev(datetime.datetime)
            prev_run = cron.get_next(datetime.datetime)
            diff = now - prev_run
            diff_seconds = diff.total_seconds()
            if 0.0 <= diff_seconds and diff_seconds <= 60.0:
                # print(row['submodule_name'], diff_seconds)
                supply(row['submodule_name'], config)


def main(config_filename):
    with open(config_filename) as config_file:
        config = yaml.load(config_file.read())
    read_own_cron('own.cron', config)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='prod.yml')
    args = parser.parse_args()
    main(args.config)
