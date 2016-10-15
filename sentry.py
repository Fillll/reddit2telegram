#enconding:utf-8

import yaml

from raven import Client


client = Client(yaml.load(open('prod.yml').read())['sentry'])


def report_error(fn):
    def wrapper(*args, **kwargs):
        try:
            fn(*args, **kwargs)
        except Exception:
            client.captureException()
            # raise
    return wrapper
