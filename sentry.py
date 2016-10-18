#enconding:utf-8
import logging
import yaml

from raven import Client

with open('prod.yml') as config_file:
    config = yaml.load(config_file.read())
# end if

if "sentry" in config:
    client = Client(config['sentry'])
else:
    client = None
    logging.info("Sentry.io not loaded")
# end if

def report_error(fn):
    def wrapper(*args, **kwargs):
        try:
            fn(*args, **kwargs)
        except Exception:
            if client:  # has sentry instance
                client.captureException()
            else:
                logging.exception("Exception Ignored.")
            # end if
        # end try
    # end def wrapper
    return wrapper
# end def report_error

