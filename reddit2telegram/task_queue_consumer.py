import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)

import concurrent.futures
import signal
import threading
from multiprocessing import cpu_count

import pymongo
import yaml

import task_queue


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


def main(config_filename):
    with open(config_filename) as config_file:
        config = yaml.safe_load(config_file.read())
    db = pymongo.MongoClient(host=config['db']['host'])[config['db']['name']]
    pool_size = config.get('pool', {}).get('size', cpu_count())
    batch_size = config.get('consumer', {}).get('batch_size', pool_size * 2)
    max_pending = config.get('consumer', {}).get('max_pending', pool_size)
    stop_event = threading.Event()

    def stop(signum, frame):
        logging.info('Received signal %d; draining workers', signum)
        stop_event.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        with _create_thread_pool(config) as executor:
            task_queue.start_consumer(
                db, executor, 5, batch_size=batch_size,
                max_pending=max_pending, stop_event=stop_event,
            )
    finally:
        db.client.close()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='configs/prod.yml')
    args = parser.parse_args()
    main(args.config)
