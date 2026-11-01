if __name__ == '__main__':
    from runtime_dispatch import dispatch
    dispatch('consumer')

import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)

import concurrent.futures
import ctypes
import signal
import threading
from multiprocessing import cpu_count

import pymongo
import yaml

import task_queue


def _limit_malloc_arenas(max_arenas):
    if not isinstance(max_arenas, int) or max_arenas < 1:
        raise ValueError('pool.malloc_arenas must be a positive integer')
    try:
        mallopt = ctypes.CDLL(None).mallopt
    except AttributeError:
        # Other platforms/allocators do not expose glibc's arena tuning API.
        logging.info('Native allocator arena tuning is unavailable')
        return False
    mallopt.argtypes = [ctypes.c_int, ctypes.c_int]
    mallopt.restype = ctypes.c_int
    # M_ARENA_MAX from malloc.h. Configure before Mongo/worker threads start.
    configured = bool(mallopt(-8, max_arenas))
    if configured:
        logging.info('Limited native allocator to %d arenas', max_arenas)
    else:
        logging.warning('Native allocator rejected arena limit')
    return configured


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
    _limit_malloc_arenas(config.get('pool', {}).get('malloc_arenas', 4))
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
