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
