"""Exercise actual TLS lifetimes and multipart streaming without external traffic."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import gc
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
import threading
import tracemalloc
import weakref
from unittest import mock

import pytest
import requests
from telegram import Bot

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'reddit2telegram'))
import utils
from utils import http_resources, memory


@pytest.fixture
def tls_server(tmp_path):
    cert, key = tmp_path / 'cert.pem', tmp_path / 'key.pem'
    subprocess.run([
        'openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
        '-subj', '/CN=localhost', '-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1',
        '-keyout', str(key), '-out', str(cert),
    ], check=True, capture_output=True)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Length', '2')
            self.end_headers()
            self.wfile.write(b'OK')

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield server, cert
    finally:
        server.shutdown()
        server.server_close()
        worker.join(2)


def test_verified_tls_context_reused_across_jobs_and_sockets_close(monkeypatch, tls_server):
    server, cert = tls_server
    context = ssl.create_default_context(cafile=str(cert))
    monkeypatch.setattr(http_resources, 'TLS_CONTEXT', context)
    sessions = []

    def job(_):
        with http_resources.media_job():
            session = http_resources.media_session()
            sessions.append(session)
            url = f'https://localhost:{server.server_port}/'
            response = session.get(url, timeout=5)
            assert response.content == b'OK'
            adapter = session.get_adapter(url)
            pool = adapter.get_connection_with_tls_context(requests.Request('GET', url).prepare(), True)
            assert pool.conn_kw['ssl_context'] is context
            assert pool.ca_certs is None
        assert len(session.get_adapter(url).poolmanager.pools) == 0

    with ThreadPoolExecutor(8) as workers:
        list(workers.map(job, range(32)))
    assert len({id(session) for session in sessions}) == 32


def test_shared_tls_still_rejects_untrusted_certificates(tls_server):
    server, cert = tls_server
    with http_resources.session() as session:
        with pytest.raises(requests.exceptions.SSLError):
            session.get(f'https://localhost:{server.server_port}/', timeout=5)
        # A caller-specified CA bundle must also keep working.
        assert session.get(f'https://localhost:{server.server_port}/', verify=str(cert), timeout=5).content == b'OK'


def test_failed_job_closes_media_session():
    with pytest.raises(RuntimeError):
        with http_resources.media_job():
            session = http_resources.media_session()
            session.close = mock.Mock(wraps=session.close)
            raise RuntimeError('failed job')
    session.close.assert_called_once()
    with http_resources.media_job():
        assert http_resources.media_session() is not session


def test_metadata_limit_closes_chunked_response_before_body_is_buffered(monkeypatch):
    response = mock.MagicMock()
    response.__enter__.return_value = response
    chunks = []

    def stream(size):
        for i in range(100):
            chunks.append(i)
            yield b'x' * size

    response.iter_content.side_effect = stream
    monkeypatch.setattr(utils, '_http_request', lambda *args, **kwargs: response)
    with pytest.raises(ValueError, match='Metadata response exceeds'):
        utils._metadata('https://example.invalid/not-actually-metadata')
    assert len(chunks) == 17
    response.__exit__.assert_called_once()


def test_large_video_reaches_http_backend_without_full_file_buffer(monkeypatch, tmp_path):
    size = 49 * 1024 * 1024
    fixture = tmp_path / 'fixture.mp4'
    with fixture.open('wb') as handle:
        handle.truncate(size)
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            remaining = int(self.headers['Content-Length'])
            received.append(remaining)
            while remaining:
                chunk = self.rfile.read(min(65536, remaining))
                assert chunk
                remaining -= len(chunk)
            body = json.dumps({'ok': True, 'result': {'message_id': 1, 'date': 0,
                'chat': {'id': -1, 'type': 'channel'},
                'video': {'file_id': 'test', 'file_unique_id': 'unique',
                          'width': 1, 'height': 1, 'duration': 1}}}).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(utils, 'short_sleep', lambda: None)
    monkeypatch.setattr(utils.Reddit2TelegramSender, '_make_mongo_connections', lambda self: None)
    monkeypatch.setattr(utils, 'TEMP_FOLDER', str(tmp_path))

    def download(url, filename):
        if filename.endswith('.aac'):
            return False
        shutil.copyfile(fixture, filename)
        return True

    monkeypatch.setattr(utils, 'download_file', download)
    try:
        with utils.Reddit2TelegramSender('@test', {'telegram': {'token': '123:local'}}) as sender:
            sender.telegram_bot = Bot('123:local', base_url=f'http://127.0.0.1:{server.server_port}/bot',
                                      request=sender._telegram_request,
                                      get_updates_request=sender._telegram_request)
            tracemalloc.start()
            try:
                assert sender.send_video('https://example.invalid/video', 'test') == utils.SupplyResult.SUCCESSFULLY
                peak = tracemalloc.get_traced_memory()[1]
            finally:
                tracemalloc.stop()
            directory = Path(sender._get_file_name('.mp4')).parent
            assert directory.exists()
        assert received and received[0] > size
        assert peak < 12 * 1024 * 1024, f'49 MiB upload allocated {peak / 2**20:.1f} MiB'
        assert not directory.exists(), 'Closed sender retained downloaded media'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


def test_maintenance_reclaims_dead_job_cycles_without_waiting_for_automatic_gc(monkeypatch):
    class Job:
        pass

    gc.collect()
    was_enabled = gc.isenabled()
    gc.disable()
    try:
        job = Job()
        job.self = job
        reference = weakref.ref(job)
        del job
        assert reference() is not None
        monkeypatch.setattr(memory, 'resident_bytes', lambda: 300 * 1024 * 1024)
        monkeypatch.setattr(memory, '_NEXT_CHECK', 0)
        memory.release_unused_memory()
        assert reference() is None
    finally:
        if was_enabled:
            gc.enable()
