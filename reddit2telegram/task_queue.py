import logging
import time
from concurrent.futures import Executor
from enum import Enum
from typing import List, Mapping

import pymongo
from bson.objectid import ObjectId
from pymongo.database import Database
from pymongo.collection import Collection

from supplier import supply


COLLECTION = 'tasks'

TASK_SUPPLY = 'supply'


logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    NEW = 1
    IN_PROGRESS = 2
    SUCCESS = 3
    FAILED = 4


def create_task_dict(task_name: str, args: Mapping):
    return {
        'name': task_name,
        'args': args,
        'status': TaskStatus.NEW.value,
        'created_at': time.time(),
        'updated_at': time.time(),
    }


def submit(mongo_database: Database, task_name: str, args: Mapping):
    task = create_task_dict()
    task_id = mongo_database[COLLECTION].insert_one(task)
    logger.info(f'Submitted task {task_id}')


def submit_batch(mongo_database: Database, task_name: str, args_list: List[Mapping]):
    tasks = map(lambda args: create_task_dict(task_name, args), args_list)
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


def execute_task(collection: Collection, id: ObjectId, name: str, args: Mapping):
    update_task_status(collection, id, TaskStatus.IN_PROGRESS)
    try:
        func = None
        if name == TASK_SUPPLY:
            func = supply
        else:
            raise Exception(f'Task {name} not found')
        func(**args)
        update_task_status(collection, id, TaskStatus.SUCCESS)
    except Exception as e:
        logger.exception(f'Task {name} failed with exception')
        update_task_status(collection, id, TaskStatus.FAILED)


def start_consumer(
    mongo_database: Database,
    executor: Executor,
    sleep_interval_seconds: float,
):
    running = True
    collection = mongo_database[COLLECTION]
    logger.info('Starting consumer %s', executor)
    while running:
        try:
            new_tasks = select_all_available_tasks(collection)
            logger.info('Found %d new tasks', len(new_tasks))
            for t in new_tasks:
                executor.submit(execute_task, collection, t['_id'], t['name'], t['args'])
            time.sleep(sleep_interval_seconds)
        except KeyboardInterrupt:
            logger.info('Stopping consumer')
            running = False
