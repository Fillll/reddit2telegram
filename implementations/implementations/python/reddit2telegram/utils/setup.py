#encoding:utf-8

import os
import yaml


def get_config(config_filename=None):
    if config_filename is None:
        config_filename = os.path.join('configs', 'prod.yml')
    with open(config_filename) as config_file:
        return yaml.safe_load(config_file.read())
