import time
from types import SimpleNamespace
from unittest import mock

import requests

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = REPO_ROOT / 'reddit2telegram'
sys.path.insert(0, str(APP_DIR))

import task_queue
import utils


class FakeCollection:
    def __init__(self, modified_count=0):
        self.modified_count = modified_count
        self.calls = []

    def update_many(self, selector, update):
        self.calls.append((selector, update))
        return SimpleNamespace(modified_count=self.modified_count)


def test_recover_abandoned_tasks_requeues_stale_non_terminal_work():
    collection = FakeCollection(modified_count=3)

    with mock.patch('task_queue.time.time', return_value=1_000):
        task_queue.recover_abandoned_tasks(collection)

    assert len(collection.calls) == 1
    selector, update = collection.calls[0]
    assert selector['status']['$in'] == [
        task_queue.TaskStatus.IN_PROGRESS.value,
        task_queue.TaskStatus.SCHEDULED.value,
    ]
    assert selector['updated_at']['$lt'] == 940
    assert update['$set']['status'] == task_queue.TaskStatus.NEW.value
    assert update['$set']['updated_at'] == 1_000


def test_fail_expired_new_tasks_marks_old_new_work_failed():
    collection = FakeCollection(modified_count=2)

    with mock.patch('task_queue.time.time', return_value=2_000):
        task_queue.fail_expired_new_tasks(collection)

    assert len(collection.calls) == 1
    selector, update = collection.calls[0]
    assert selector['status'] == task_queue.TaskStatus.NEW.value
    assert selector['created_at']['$lt'] == 500
    assert update['$set']['status'] == task_queue.TaskStatus.FAILED.value
    assert update['$set']['updated_at'] == 2_000


def test_claim_available_tasks_claims_bounded_tasks_atomically():
    class FakeClaimCollection:
        def __init__(self):
            self.tasks = [
                {
                    '_id': 'one',
                    'name': task_queue.TASK_SUPPLY,
                    'args': {'submodule_name': 'r_one'},
                    'status': task_queue.TaskStatus.NEW.value,
                    'created_at': 900,
                },
                {
                    '_id': 'two',
                    'name': task_queue.TASK_SUPPLY,
                    'args': {'submodule_name': 'r_two'},
                    'status': task_queue.TaskStatus.NEW.value,
                    'created_at': 901,
                },
            ]
            self.calls = []

        def find_one_and_update(self, selector, update, **kwargs):
            self.calls.append((selector, update, kwargs))
            for task in self.tasks:
                if (
                    task['status'] == selector['status']
                    and task['created_at'] >= selector['created_at']['$gte']
                ):
                    task.update(update['$set'])
                    return dict(task)
            return None

    collection = FakeClaimCollection()

    with mock.patch('task_queue.time.time', return_value=1_000):
        claimed = task_queue.claim_available_tasks(collection, limit=1)

    assert [task['_id'] for task in claimed] == ['one']
    assert collection.tasks[0]['status'] == task_queue.TaskStatus.SCHEDULED.value
    assert collection.tasks[1]['status'] == task_queue.TaskStatus.NEW.value
    assert len(collection.calls) == 1


def test_hydrate_supply_args_loads_config_file(tmp_path):
    config_file = tmp_path / 'prod.yml'
    config_file.write_text(
        'db:\n'
        '  host: localhost\n'
        '  name: reddit2telegram\n',
        encoding='utf-8'
    )

    args = task_queue._hydrate_supply_args({
        'submodule_name': 'r_python',
        'config_filename': str(config_file),
    })

    assert args == {
        'submodule_name': 'r_python',
        'config': {
            'db': {
                'host': 'localhost',
                'name': 'reddit2telegram',
            }
        },
    }


def test_get_url_returns_other_when_head_request_fails():
    submission = SimpleNamespace(
        url='https://example.com/image.jpg',
        is_video=False,
        media=None,
        crosspost_parent_list=[],
        is_self=False,
    )

    with mock.patch(
        'utils._http_request',
        side_effect=requests.RequestException('timeout'),
    ):
        what, url = utils.get_url(submission)

    assert what == utils.TYPE_OTHER
    assert url == 'https://example.com/image.jpg'


def test_get_url_size_returns_zero_when_head_request_fails():
    with mock.patch(
        'utils._http_request',
        side_effect=requests.RequestException('timeout'),
    ):
        assert utils.get_url_size('https://example.com/file.mp4') == 0


def test_shared_database_reuses_single_mongo_client():
    utils._MONGO_DATABASES.clear()
    calls = []

    class FakeClient:
        def __init__(self, host):
            calls.append(host)

        def __getitem__(self, name):
            return {'db_name': name}

    config = {'db': {'host': 'localhost', 'name': 'reddit2telegram'}}

    with mock.patch('utils.pymongo.MongoClient', FakeClient):
        db_one = utils._get_shared_database(config)
        db_two = utils._get_shared_database(config)

    assert db_one == {'db_name': 'reddit2telegram'}
    assert db_two == db_one
    assert calls == ['localhost']


def test_reddit2telegram_sender_close_closes_event_loop():
    utils._MONGO_DATABASES.clear()
    config = {
        'telegram': {'token': '123:abc'},
        'db': {'host': 'localhost', 'name': 'reddit2telegram'},
    }

    class FakeClient:
        def __init__(self, host):
            pass

        def __getitem__(self, name):
            return {
                'stats': object(),
                'urls': object(),
                'contents': object(),
                'errors': object(),
                'tasks': object(),
                'settings': object(),
            }

    with mock.patch('utils.short_sleep'), mock.patch('utils.pymongo.MongoClient', FakeClient):
        sender = utils.Reddit2TelegramSender('@r_channels_test', config)

    loop = sender._loop
    sender.close()

    assert loop.is_closed()
    utils._MONGO_DATABASES.clear()
