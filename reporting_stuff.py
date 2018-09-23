#enconding:utf-8
import logging
import sys
import os

import yaml
from raven import Client
from raven.handlers.logging import SentryHandler
from raven.conf import setup_logging

import utils


with open(os.path.join('configs', 'prod.yml')) as config_file:
    config = yaml.load(config_file.read())


if 'sentry' in config:
    client = Client(config['sentry'], auto_log_stacks=True)
    handler = SentryHandler(client)
    setup_logging(handler)
else:
    client = None
    logging.info('Sentry.io not loaded')


def send_report_to_dev_chat(exc):
    r2t = utils.Reddit2TelegramSender(config['telegram']['dev_chat'], config)
    local_vars = sys.exc_info()[2].tb_next.tb_frame.f_locals
    submodule = local_vars['submodule_name']
    channel = local_vars['submodule'].t_channel
    title = 'submodule: {}\nchannel: {}'.format(submodule, channel)
    if 'submission' in local_vars:
        link = local_vars['submission'].shortlink
        error_cnt = r2t.store_error_link(channel, link)
        title = '{title}\nlink: {link}\nerror_cnt: {cnt}'.format(
            title=title,
            link=link,
            cnt=error_cnt['cnt']
        )
    report = '{t}\n\n\n{e}'.format(
        t=title,
        e=exc
    )
    r2t.send_text(report)


def report_error(fn):
    def wrapper(*args, **kwargs):
        try:
            fn(*args, **kwargs)
        except Exception as e:
            if client:  # has sentry instance
                client.captureException()
            else:
                logging.exception('Exception Ignored.')
            send_report_to_dev_chat(e)
    return wrapper
