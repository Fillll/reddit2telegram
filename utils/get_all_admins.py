#encoding:utf-8

import csv
import logging
import time
import importlib

import yaml

from utils import Reddit2TelegramSender


logger = logging.getLogger(__name__)


def get_names(admins):
    admins_names = list()
    for admin in admins:
        user = admin['user']
        if 'username' in user:
            username = user['username']
            if username != 'reddit2telegram_bot':
                admins_names.append('@' + username)
        else:
            admins_names.append('%NO_USERNAME%')
    return admins_names


def read_cron_and_get_admins(own_cron_filename, output_filename, config):
    with open(own_cron_filename) as cron_tsv_file, open(output_filename, 'w') as output_admin_file:
        tsv_reader = csv.DictReader(cron_tsv_file, delimiter='\t')
        r2t = Reddit2TelegramSender('@r_channels_test', config)
        tsv_writer = csv.DictWriter(output_admin_file, delimiter='\t', fieldnames=['SUBMODULE', 'CHANNEL', 'ADMINS'])
        tsv_writer.writeheader()
        for row in tsv_reader:
            submodule = importlib.import_module('channels.{}.app'.format(row['submodule_name']))
            channel = submodule.t_channel
            admins = r2t.telepot_bot.getChatAdministrators(channel)
            results = {'CHANNEL': channel, 'ADMINS': ', '.join(get_names(admins)), 'SUBMODULE': row['submodule_name']}
            print(results)
            tsv_writer.writerow(results)
            time.sleep(2)


def main(config_filename, output_filename):
    with open(config_filename) as config_file:
        config = yaml.load(config_file.read())
        read_cron_and_get_admins('own.cron', output_filename, config)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='configs/prod.yml')
    parser.add_argument('--output', default='admins_list.tsv')
    args = parser.parse_args()
    main(args.config, args.output)