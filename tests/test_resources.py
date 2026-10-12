import asyncio
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import sys
import subprocess
import json

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'reddit2telegram'))
import supplier
import task_queue
import utils
import task_queue_consumer


def make_sender(monkeypatch):
    monkeypatch.setattr(utils.Reddit2TelegramSender, '_make_mongo_connections', lambda self: None)
    monkeypatch.setattr(utils, 'short_sleep', lambda: None)
    return utils.Reddit2TelegramSender('@test', {'telegram': {'token': '123:local-test'}})


def test_sender_closes_live_connection_without_bot_initialize(monkeypatch):
    disconnected = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Length', '2')
            self.end_headers()
            self.wfile.write(b'OK')

        def finish(self):
            super().finish()
            disconnected.set()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    sender = make_sender(monkeypatch)
    try:
        response = sender._run_async(sender._telegram_request._client.get(
            f'http://127.0.0.1:{server.server_port}/'
        ))
        assert response.status_code == 200
        assert not sender.telegram_bot._initialized
        assert not sender._telegram_request._client.is_closed
        sender.close()
        sender.close()
        assert sender._telegram_request._client.is_closed
        assert sender._loop.is_closed()
        assert disconnected.wait(2), 'The keepalive connection was not closed'
    finally:
        sender.close()
        server.shutdown()
        server.server_close()
        thread.join(2)


def test_sender_reuses_tls_context_and_one_transport(monkeypatch):
    senders = [make_sender(monkeypatch) for _ in range(3)]
    try:
        for sender in senders:
            assert sender.telegram_bot._request[0] is sender.telegram_bot._request[1]
            assert sender._telegram_request._client._transport._pool._ssl_context is utils._TELEGRAM_SSL_CONTEXT
    finally:
        for sender in senders:
            sender.close()


def test_sender_constructor_failure_closes_transport(monkeypatch):
    request = utils._TelegramRequest()
    monkeypatch.setattr(utils, '_TelegramRequest', lambda **kwargs: request)
    monkeypatch.setattr(utils.Reddit2TelegramSender, '_make_mongo_connections',
                        mock.Mock(side_effect=RuntimeError('database unavailable')))
    with pytest.raises(RuntimeError, match='database unavailable'):
        utils.Reddit2TelegramSender('@test', {'telegram': {'token': '123:local-test'}})
    assert request._client.is_closed


@pytest.mark.parametrize('fail', [False, True])
def test_reddit_session_closed_after_success_or_failure(fail):
    session = requests.Session()
    session.close = mock.Mock(wraps=session.close)
    submission = SimpleNamespace(shortlink='https://redd.it/test')
    reddit = mock.Mock()
    reddit.subreddit.return_value.hot.return_value = iter([submission])
    sender = mock.MagicMock()
    sender.__enter__.return_value = sender
    sender.was_before.return_value = False
    sender.too_much_errors.return_value = False
    config = {'reddit': dict.fromkeys(
        ['user_agent', 'client_id', 'client_secret', 'username', 'password'], 'test'
    )}
    post = mock.Mock(side_effect=RuntimeError('send failed')) if fail else mock.Mock(
        return_value=utils.SupplyResult.SUCCESSFULLY
    )
    with mock.patch('supplier.requests.Session', return_value=session), mock.patch(
        'supplier.praw.Reddit', return_value=reddit
    ) as constructor, mock.patch('supplier.utils.Reddit2TelegramSender', return_value=sender):
        if fail:
            with pytest.raises(RuntimeError, match='send failed'):
                supplier.send_to_channel_from_subreddit(post, '@test', 'test', 'hot', 100, config)
        else:
            supplier.send_to_channel_from_subreddit(post, '@test', 'test', 'hot', 100, config)
    assert constructor.call_args.kwargs['requestor_kwargs']['session'] is session
    session.close.assert_called_once()


def test_consumer_keeps_excess_work_in_database_and_releases_completed_slots():
    futures = []
    claim_limits = []

    class Stop:
        ticks = 0

        def is_set(self):
            return self.ticks >= 3

        def wait(self, seconds):
            self.ticks += 1
            if self.ticks == 2:
                futures[0].set_result(None)

    def claim(collection, limit):
        claim_limits.append(limit)
        return [{'_id': str(i), 'name': 'supply', 'args': {}} for i in range(limit)]

    def submit(*args):
        future = Future()
        futures.append(future)
        return future

    executor = mock.Mock(submit=mock.Mock(side_effect=submit))
    with mock.patch('task_queue.recover_abandoned_tasks'), mock.patch(
        'task_queue.fail_expired_new_tasks'
    ), mock.patch('task_queue.claim_available_tasks', side_effect=claim):
        task_queue.start_consumer({'tasks': object()}, executor, 0, batch_size=100,
                                  max_pending=2, stop_event=Stop())
    assert claim_limits == [2, 1]
    assert executor.submit.call_count == 3
    assert sum(not future.done() for future in futures) == 2


def test_video_uploads_are_limited_across_worker_threads(monkeypatch, tmp_path):
    active = 0
    peak = 0
    lock = threading.Lock()

    async def upload(**kwargs):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        try:
            await asyncio.sleep(0.05)
        finally:
            with lock:
                active -= 1

    def download(url, filename):
        if filename.endswith('.aac'):
            return False
        Path(filename).write_bytes(b'video')
        return True

    monkeypatch.setattr(utils, 'download_file', download)
    senders = []
    for i in range(12):
        sender = object.__new__(utils.Reddit2TelegramSender)
        sender.t_channel = f'@test{i}'
        sender.telegram_bot = SimpleNamespace(send_video=upload)
        sender._get_file_name = lambda ext, i=i: str(tmp_path / f'{i}{ext}')
        sender._run_async = asyncio.run
        senders.append(sender)
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(lambda sender: sender.send_video('https://local/video', 'test'), senders))
    assert all(result == utils.SupplyResult.SUCCESSFULLY for result in results)
    assert 2 <= peak <= 4
    assert active == 0


def test_native_allocator_arena_limit_with_32_workers(tmp_path):
    # Use a fresh interpreter so this test does not tune pytest's allocator.
    code = r'''
import ctypes, gc, json, ssl, sys, threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import task_queue_consumer

if not task_queue_consumer._limit_malloc_arenas(4):
    sys.exit(77)
barrier = threading.Barrier(32)
def allocate(_):
    barrier.wait()
    for i in range(3):
        context = ssl.create_default_context()
    del context
with ThreadPoolExecutor(32) as pool:
    list(pool.map(allocate, range(32)))
gc.collect()
libc = ctypes.CDLL(None)
libc.fopen.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
libc.fopen.restype = ctypes.c_void_p
libc.malloc_info.argtypes = [ctypes.c_int, ctypes.c_void_p]
libc.fclose.argtypes = [ctypes.c_void_p]
stream = libc.fopen(sys.argv[1].encode(), b'w')
assert stream
try:
    assert libc.malloc_info(0, stream) == 0
finally:
    libc.fclose(stream)
print(json.dumps({'arenas': Path(sys.argv[1]).read_text().count('<heap nr=')}))
'''
    app_dir = Path(__file__).resolve().parent.parent / 'reddit2telegram'
    result = subprocess.run([sys.executable, '-c', code, str(tmp_path / 'malloc.xml')],
                            cwd=app_dir, capture_output=True, text=True, timeout=60)
    if result.returncode == 77:
        pytest.skip('Native allocator does not support arena tuning')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['arenas'] <= 4


@pytest.mark.parametrize('value', [0, -1, '4'])
def test_invalid_native_arena_limit(value):
    with pytest.raises(ValueError, match='positive integer'):
        task_queue_consumer._limit_malloc_arenas(value)
