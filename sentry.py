#enconding:utf-8
import logging
import sys

import yaml
from raven import Client
from raven.handlers.logging import SentryHandler
from raven.conf import setup_logging

import utils


with open('prod.yml') as config_file:
    config = yaml.load(config_file.read())


if 'sentry' in config:
    client = Client(config['sentry'], auto_log_stacks=True)
    handler = SentryHandler(client)
    setup_logging(handler)
else:
    client = None
    logging.info('Sentry.io not loaded')


def send_report_to_dev_chat(exc):
    r2t = utils.Reddit2TelegramSender(config['telegram_dev_chat'], config)
    local_vars = sys.exc_info()[2].tb_next.tb_frame.f_locals
    submodule = local_vars['submodule_name']
    channel = local_vars['submodule'].t_channel
    title = 'submodule: {}\nchannel: {}'.format(submodule, channel)
    if 'submission' in local_vars:
        link = local_vars['submission'].shortlink
        title = '{}\nlink: {}'.format(title, link)
    report = '{}\n\n\n{}'.format(
        title,
        str(exc)
    )
    r2t.send_text(report)


def report_error(fn):
    def wrapper(*args, **kwargs):
        try:
            fn(*args, **kwargs)
        except Exception as e:
            send_report_to_dev_chat(e)
            if client:  # has sentry instance
                client.captureException()
            else:
                logging.exception('Exception Ignored.')
    return wrapper
