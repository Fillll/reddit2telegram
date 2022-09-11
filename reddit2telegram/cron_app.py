#encoding:utf-8

import datetime
import csv
import logging
from multiprocessing import Process
import time
import math
import random

import yaml
from croniter import croniter
import psutil

from supplier import supply


logger = logging.getLogger(__name__)
free_memory_constant = 128.821


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
        cycles = 0
        random.shuffle(list_of_processes_to_start)
        for process_to_start in list_of_processes_to_start:
            successfully_started = False
            while not successfully_started:
                cycles += 1
                cycles_factor = math.ceil(cycles / 45)
                time.sleep(1)
                free_memory_mb = psutil.virtual_memory().free / 1024**2
                if free_memory_mb > free_memory_constant * min(cycles_factor, 3):
                    supplying_process = Process(target=supply, args=(process_to_start, config))
                    supplying_process.start()
                    successfully_started = True
                    break
                else:
                    successfully_started = False


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
