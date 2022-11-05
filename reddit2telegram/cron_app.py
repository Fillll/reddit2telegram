#encoding:utf-8

import datetime
import csv
import concurrent.futures
import logging
from multiprocessing import cpu_count
import random

import yaml
from croniter import croniter

from supplier import supply


logger = logging.getLogger(__name__)


def _create_thread_pool(config) -> concurrent.futures.Executor:
    pool_config = config.get('pool', {})
    pool_class = pool_config.get('class', 'ProcessPoolExecutor')
    size = pool_config.get('size', cpu_count())
    if pool_class == 'ThreadPoolExecutor':
        return concurrent.futures.ThreadPoolExecutor(size)
    elif pool_class == 'ProcessPoolExecutor':
        return concurrent.futures.ProcessPoolExecutor(size)
    else:
        raise ValueError(f"Invalid pool class name: {pool_class}")


def _process_single_entry(
    submodule_name,
    config,
    is_test=False,
):
    try:
        return supply(submodule_name, config, is_test)
    except:
        # supply() does its own logging and reports errors to Sentry
        pass


def read_own_cron(own_cron_filename, config):
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
                list_of_processes_to_start.append(row['submodule_name'])
    random.shuffle(list_of_processes_to_start)
    executor = _create_thread_pool(config)
    executor.map(
        lambda submodule_name: _process_single_entry(submodule_name, config),
        list_of_processes_to_start
    )


def main(config_filename):
    with open(config_filename) as config_file:
        config = yaml.safe_load(config_file.read())
        read_own_cron(config['cron_file'], config)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='configs/prod.yml')
    args = parser.parse_args()
    main(args.config)
