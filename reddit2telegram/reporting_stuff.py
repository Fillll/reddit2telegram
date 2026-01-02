#enconding:utf-8
import logging
import sys
import os

import yaml
from raven import Client
from raven.handlers.logging import SentryHandler
from raven.conf import setup_logging

import utils


CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'configs', 'prod.yml')
with open(CONFIG_PATH) as config_file:
    config = yaml.safe_load(config_file.read())


if 'sentry' in config:
    client = Client(config['sentry'], auto_log_stacks=True)
    handler = SentryHandler(client)
    setup_logging(handler)
else:
    client = None
    logging.info('Sentry.io not loaded')


def send_report_to_dev_chat(exc):
    link = None
    r2t = utils.Reddit2TelegramSender(config['telegram']['dev_chat'], config)
    frame = sys.exc_info()[2]
    frame = frame.tb_next
    while frame:
        local_vars = frame.tb_frame.f_locals
        if ('submodule_name' in local_vars) and ('submodule' in local_vars):
            submodule = local_vars['submodule_name']
            channel = local_vars['submodule'].t_channel
            title = 'submodule: {}\nchannel: {}'.format(submodule, channel)
        if 'submission' in local_vars:
            link = local_vars['submission'].shortlink
        frame = frame.tb_next
    if link is not None:
        error_cnt = r2t.store_error_link(channel, link)
        title = '{title}\nlink: {link}\nerror_cnt: {cnt}'.format(
                    title=title,
                    link=link,
                    cnt=error_cnt['cnt']
                )
    else:
        error_cnt = r2t.store_error_no_link(channel)
        title = '{title}\nerror_cnt: {cnt}'.format(
                    title=title,
                    cnt=error_cnt['cnt']
                )

    report = '<b>r2t error</b>\n{t}\n\n\n<pre>{e}</pre>'.format(
        t=title,
        e=exc
    )
    r2t.send_text(report, parse_mode='HTML')


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
