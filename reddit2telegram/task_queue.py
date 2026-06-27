import logging
import time
from concurrent.futures import Executor
from enum import Enum
from typing import List, Mapping

import pymongo
from bson.objectid import ObjectId
from pymongo.database import Database
from pymongo.collection import Collection
from pymongo.collection import ReturnDocument
import yaml

from supplier import supply


COLLECTION = 'tasks'

TASK_SUPPLY = 'supply'

ABANDONED_TASK_MIN_AGE_SECONDS = 60
TASK_MAX_AGE_SECONDS = 25 * 60
CLAIM_BATCH_SIZE = 100


logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    NEW = 1
    IN_PROGRESS = 2
    SUCCESS = 3
    FAILED = 4
    SCHEDULED = 5


def create_task_dict(task_name: str, args: Mapping, now=None):
    if now is None:
        now = time.time()
    return {
        'name': task_name,
        'args': args,
        'status': TaskStatus.NEW.value,
        'created_at': now,
        'updated_at': now,
    }


def submit(mongo_database: Database, task_name: str, args: Mapping):
    task = create_task_dict(task_name, args)
    result = mongo_database[COLLECTION].insert_one(task)
    logger.info(f'Submitted task {result.inserted_id}')


def submit_batch(mongo_database: Database, task_name: str, args_list: List[Mapping]):
    args_list = list(args_list)
    if not args_list:
        logger.info('No tasks to submit')
        return
    now = time.time()
    tasks = [create_task_dict(task_name, args, now=now) for args in args_list]
    result = mongo_database[COLLECTION].insert_many(tasks)
    logger.info(f"Inserted {len(result.inserted_ids)} tasks")


def update_task_status(collection: Collection, id: ObjectId, new_status: TaskStatus):
    result = collection.update_one({'_id': id}, {
        '$set': {
            'status': new_status.value,
            'updated_at': time.time(),
        },
    })
    logger.info('Modified %d docs', result.modified_count)


def select_all_available_tasks(collection: Collection):
    return list(collection.find({
        'status': TaskStatus.NEW.value,
    }, sort=[('created_at', pymongo.ASCENDING)]))


def fail_expired_new_tasks(collection: Collection):
    cutoff = time.time() - TASK_MAX_AGE_SECONDS
    result = collection.update_many(
        {
            'status': TaskStatus.NEW.value,
            'created_at': {'$lt': cutoff},
        },
        {
            '$set': {
                'status': TaskStatus.FAILED.value,
                'updated_at': time.time(),
            },
        }
    )
    if result.modified_count:
        logger.warning('Failed %d expired new tasks', result.modified_count)


def claim_available_tasks(collection: Collection, limit: int = CLAIM_BATCH_SIZE):
    claimed_tasks = []
    cutoff = time.time() - TASK_MAX_AGE_SECONDS
    for _ in range(limit):
        task = collection.find_one_and_update(
            {
                'status': TaskStatus.NEW.value,
                'created_at': {'$gte': cutoff},
            },
            {
                '$set': {
                    'status': TaskStatus.SCHEDULED.value,
                    'updated_at': time.time(),
                },
            },
            sort=[('created_at', pymongo.ASCENDING)],
            projection={
                'name': True,
                'args': True,
                'created_at': True,
            },
            return_document=ReturnDocument.AFTER,
        )
        if task is None:
            break
        claimed_tasks.append(task)
    return claimed_tasks


def recover_abandoned_tasks(collection: Collection):
    cutoff = time.time() - ABANDONED_TASK_MIN_AGE_SECONDS
    result = collection.update_many(
        {
            'status': {
                '$in': [
                    TaskStatus.IN_PROGRESS.value,
                    TaskStatus.SCHEDULED.value,
                ]
            },
            'updated_at': {'$lt': cutoff},
        },
        {
            '$set': {
                'status': TaskStatus.NEW.value,
                'updated_at': time.time(),
            },
        }
    )
    if result.modified_count:
        logger.warning('Recovered %d abandoned tasks', result.modified_count)


def _hydrate_supply_args(args: Mapping):
    if 'config' in args:
        return args
    if 'config_filename' not in args:
        return args
    hydrated_args = dict(args)
    config_filename = hydrated_args.pop('config_filename')
    with open(config_filename) as config_file:
        hydrated_args['config'] = yaml.safe_load(config_file.read())
    return hydrated_args


def execute_task(collection: Collection, id: ObjectId, name: str, args: Mapping):
    update_task_status(collection, id, TaskStatus.IN_PROGRESS)
    try:
        func = None
        if name == TASK_SUPPLY:
            func = supply
            args = _hydrate_supply_args(args)
        else:
            raise Exception(f'Task {name} not found')
        func(**args)
        update_task_status(collection, id, TaskStatus.SUCCESS)
        logger.info(f'Task {name} successfully executed.')
    except Exception as e:
        logger.exception(f'Task {name} failed with exception')
        update_task_status(collection, id, TaskStatus.FAILED)


def start_consumer(
    mongo_database: Database,
    executor: Executor,
    sleep_interval_seconds: float,
    batch_size: int = CLAIM_BATCH_SIZE,
):
    running = True
    collection = mongo_database[COLLECTION]
    recover_abandoned_tasks(collection)
    logger.info('Starting consumer %s', executor)
    while running:
        try:
            fail_expired_new_tasks(collection)
            new_tasks = claim_available_tasks(collection, batch_size)
            logger.info('Claimed %d new tasks', len(new_tasks))
            for t in new_tasks:
                executor.submit(execute_task, collection, t['_id'], t['name'], t['args'])
            time.sleep(sleep_interval_seconds)
        except KeyboardInterrupt:
            logger.info('Stopping consumer')
            running = False
