"""Opt-in integration tests: real Telegram delivery, Reddit, and resource cleanup."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import functools
import gc
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
import uuid
import os

import psutil
import requests
from telegram import Bot, Message
import yaml

APP_DIR = Path(__file__).resolve().parent.parent / 'reddit2telegram'
sys.path.insert(0, str(APP_DIR))
import supplier
import task_queue_consumer
import utils

# Telegram request URLs contain the bot token.
logging.getLogger('httpx').setLevel(logging.WARNING)
TEST_CHANNEL = '@r_channels_test'


class LiveState:
    def __init__(self):
        self.lock = threading.Lock()
        self.next_send = 0.0
        self.active_uploads = 0
        self.peak_uploads = 0

    def reserve_send(self):
        # Also respect Telegram's per-group limit if the test chat is a group.
        with self.lock:
            now = time.monotonic()
            start = max(now, self.next_send)
            self.next_send = start + 3.1
            return start - now

    async def pace(self):
        await asyncio.sleep(self.reserve_send())


class RecordingBot(Bot):
    def __init__(self, state, **kwargs):
        super().__init__(**kwargs)
        object.__setattr__(self, 'state', state)

    async def send_message(self, **kwargs):
        await self.state.pace()
        return await super().send_message(**kwargs)

    async def send_photo(self, **kwargs):
        await self.state.pace()
        return await super().send_photo(**kwargs)

    async def send_document(self, **kwargs):
        await self.state.pace()
        return await super().send_document(**kwargs)

    async def send_media_group(self, **kwargs):
        await self.state.pace()
        return await super().send_media_group(**kwargs)

    async def send_video(self, **kwargs):
        with self.state.lock:
            self.state.active_uploads += 1
            self.state.peak_uploads = max(self.state.peak_uploads, self.state.active_uploads)
        try:
            await self.state.pace()
            return await super().send_video(**kwargs)
        finally:
            with self.state.lock:
                self.state.active_uploads -= 1


class RecordingSender(utils.Reddit2TelegramSender):
    def __init__(self, config, root, state):
        self.messages = []
        self.media_paths = set()
        self.root = root / uuid.uuid4().hex
        self.root.mkdir()
        super().__init__(TEST_CHANNEL, config)
        self.telegram_bot = RecordingBot(
            state, token=config['telegram']['token'],
            request=self._telegram_request, get_updates_request=self._telegram_request,
        )

    def _get_file_name(self, ext='file'):
        # Exercise production's actual private directory and cleanup lifecycle.
        filename = super()._get_file_name(ext)
        self.media_paths.add(Path(filename))
        return filename

    def _run_async(self, coro):
        result = super()._run_async(coro)
        if isinstance(result, Message):
            self.messages.append(result)
        elif isinstance(result, (tuple, list)):
            self.messages.extend(message for message in result if isinstance(message, Message))
        return result


class LiveResourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.getenv('R2T_LIVE_TESTS') != '1':
            raise unittest.SkipTest('Set R2T_LIVE_TESTS=1 to send to @r_channels_test.')
        if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
            raise RuntimeError('ffmpeg and ffprobe are required for the live media tests')
        with (APP_DIR / 'configs/prod.yml').open() as stream:
            cls.config = yaml.safe_load(stream)
        task_queue_consumer._limit_malloc_arenas(4)
        cls.state = LiveState()
        cls.run_id = uuid.uuid4().hex[:8]
        directory = tempfile.TemporaryDirectory(prefix='r2t-live-tests-')
        cls.addClassCleanup(directory.cleanup)
        cls.root = Path(directory.name)
        cls._generate_media()

        class QuietHandler(SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass

        cls.server = ThreadingHTTPServer(
            ('127.0.0.1', 0), functools.partial(QuietHandler, directory=str(cls.root))
        )
        cls.addClassCleanup(cls.server.server_close)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.addClassCleanup(cls.server.shutdown)
        cls.video_url = f'http://127.0.0.1:{cls.server.server_port}/DASH_720.mp4'
        # Verify the configured bot can post, before attempting the test sends.
        with cls.sender() as sender:
            cls.chat = sender._run_async(sender.telegram_bot.get_chat(TEST_CHANNEL))
            bot = sender._run_async(sender.telegram_bot.get_me())
            member = sender._run_async(sender.telegram_bot.get_chat_member(cls.chat.id, bot.id))
            if cls.chat.type == 'channel' and not getattr(member, 'can_post_messages', False):
                raise RuntimeError('The configured bot needs posting rights in @r_channels_test')
            # Warm the shared Mongo connections before measuring descriptors.
            utils._get_shared_database(cls.config).command('ping')

    @classmethod
    def _generate_media(cls):
        def ffmpeg(*args):
            subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', *args],
                           check=True, capture_output=True, timeout=30)

        ffmpeg('-f', 'lavfi', '-i', 'color=c=blue:s=128x128', '-frames:v', '1',
               '-threads', '1', str(cls.root / 'photo.png'))
        ffmpeg('-f', 'lavfi', '-i', 'testsrc=size=128x128:rate=5', '-t', '1',
               '-threads', '1', str(cls.root / 'animation.gif'))
        ffmpeg('-f', 'lavfi', '-i', 'testsrc=size=160x120:rate=10', '-t', '1',
               '-an', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-threads', '1',
               str(cls.root / 'DASH_720.mp4'))
        ffmpeg('-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=44100', '-t', '1',
               '-c:a', 'aac', str(cls.root / 'DASH_AUDIO_128.mp4'))

    @classmethod
    def sender(cls):
        return RecordingSender(cls.config, cls.root, cls.state)

    def caption(self, name):
        return f'r2t live test {self.run_id}: {name}'

    def assert_delivery(self, message):
        self.assertEqual(message.chat.id, self.chat.id)
        self.assertGreater(message.message_id, 0)

    def assert_closed(self, sender):
        self.assertTrue(sender._telegram_request._client.is_closed)
        self.assertTrue(sender._loop.is_closed())

    def test_repeated_jobs_release_clients_and_descriptors(self):
        process = psutil.Process()
        before = process.num_fds()
        senders = []
        for i in range(6):
            with self.sender() as sender:
                text = self.caption(f'repeated job {i + 1}/6')
                self.assertEqual(sender.send_text(text), utils.SupplyResult.SUCCESSFULLY)
                self.assert_delivery(sender.messages[-1])
                self.assertEqual(sender.messages[-1].text, text)
            self.assert_closed(sender)
            senders.append(sender)  # Keep objects alive so GC cannot hide a leak.
        gc.collect()
        self.assertLessEqual(process.num_fds(), before + 3, 'Descriptors accumulated after closed jobs')

    def test_exception_after_real_send_still_closes_client(self):
        with self.assertRaisesRegex(RuntimeError, 'intentional test interruption'):
            with self.sender() as sender:
                sender.send_text(self.caption('cleanup after exception'))
                self.assert_delivery(sender.messages[-1])
                raise RuntimeError('intentional test interruption')
        self.assert_closed(sender)

    def test_real_photo_upload_and_r2t_delivery(self):
        with self.sender() as sender:
            uploaded = sender._run_async(sender.telegram_bot.send_photo(
                chat_id=TEST_CHANNEL, photo=(self.root / 'photo.png').read_bytes(),
                caption=self.caption('photo fixture upload'),
            ))
            self.assert_delivery(uploaded)
            self.assertTrue(uploaded.photo)
            result = sender.send_img(uploaded.photo[-1].file_id, self.caption('r2t photo delivery'))
            self.assertEqual(result, utils.SupplyResult.SUCCESSFULLY)
            self.assert_delivery(sender.messages[-1])
            self.assertTrue(sender.messages[-1].photo)
        self.assert_closed(sender)

    def test_real_gif_upload_and_r2t_delivery(self):
        with self.sender() as sender:
            uploaded = sender._run_async(sender.telegram_bot.send_document(
                chat_id=TEST_CHANNEL, document=(self.root / 'animation.gif').read_bytes(),
                filename='r2t-live-test.gif', caption=self.caption('GIF fixture upload'),
            ))
            self.assert_delivery(uploaded)
            self.assertIsNotNone(uploaded.document)
            result = sender.send_gif(uploaded.document.file_id, self.caption('r2t GIF delivery'))
            self.assertEqual(result, utils.SupplyResult.SUCCESSFULLY)
            self.assert_delivery(sender.messages[-1])
            self.assertIsNotNone(sender.messages[-1].document)
        self.assert_closed(sender)

    def test_real_video_download_audio_merge_and_delivery(self):
        with self.sender() as sender:
            result = sender.send_video(self.video_url, self.caption('video with merged audio'))
            self.assertEqual(result, utils.SupplyResult.SUCCESSFULLY)
            message = sender.messages[-1]
            self.assert_delivery(message)
            self.assertIsNotNone(message.video)
            self.assertTrue(sender.media_paths)
            self.assertTrue(all(not path.parent.exists() for path in sender.media_paths),
                            'A completed upload retained its production temporary directory')
            # Inspect what Telegram actually received after local media cleanup.
            delivered = sender.root / 'delivered.mp4'
            remote = sender._run_async(sender.telegram_bot.get_file(message.video.file_id))
            sender._run_async(remote.download_to_drive(custom_path=delivered))
            probe = subprocess.run([
                'ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type', '-of', 'json',
                str(delivered),
            ], check=True, capture_output=True, text=True, timeout=10)
            self.assertEqual({stream['codec_type'] for stream in json.loads(probe.stdout)['streams']},
                             {'audio', 'video'})
        self.assert_closed(sender)

    def test_concurrent_real_video_jobs_respect_upload_limit(self):
        self.state.peak_uploads = 0

        def send(i):
            with self.sender() as sender:
                result = sender.send_video(self.video_url, self.caption(f'concurrent video {i + 1}/6'))
                self.assertEqual(result, utils.SupplyResult.SUCCESSFULLY)
                self.assert_delivery(sender.messages[-1])
                self.assertIsNotNone(sender.messages[-1].video)
            self.assert_closed(sender)
            return sender.messages[-1].message_id

        with ThreadPoolExecutor(max_workers=6) as pool:
            message_ids = list(pool.map(send, range(6)))
        self.assertEqual(len(set(message_ids)), 6)
        self.assertLessEqual(self.state.peak_uploads, 2)
        self.assertEqual(self.state.active_uploads, 0)

    def test_real_gallery_delivery_is_confirmed(self):
        with self.sender() as sender:
            uploaded = sender._run_async(sender.telegram_bot.send_photo(
                chat_id=TEST_CHANNEL, photo=(self.root / 'photo.png').read_bytes(),
                caption=self.caption('gallery fixture upload'),
            ))
            file_id = uploaded.photo[-1].file_id
            result = sender.send_gallery({0: {
                0: {'type': 'pic', 'url': file_id}, 1: {'type': 'pic', 'url': file_id},
            }}, self.caption('gallery delivery'))
            self.assertEqual(result, utils.SupplyResult.SUCCESSFULLY)
            group = [message for message in sender.messages if message.media_group_id]
            self.assertEqual(len(group), 2, 'Gallery reported success without delivered photos')
            self.assertEqual(group[0].media_group_id, group[1].media_group_id)
            for message in group:
                self.assert_delivery(message)
        self.assert_closed(sender)

    def test_live_reddit_to_telegram_supply_closes_resources(self):
        sessions = []
        original_session = requests.Session

        class TrackingSession(original_session):
            def __init__(self):
                super().__init__()
                self.closed = False
                sessions.append(self)

            def close(self):
                self.closed = True
                super().close()

        senders = []
        messages = []

        def post(submission, sender):
            time.sleep(self.state.reserve_send())
            senders.append(sender)
            message = sender._run_async(sender.telegram_bot.send_message(
                chat_id=TEST_CHANNEL,
                text=self.caption('live Reddit supply') + '\n' + submission.title + '\n' + submission.shortlink,
            ))
            messages.append(message)
            return utils.SupplyResult.SUCCESSFULLY

        # Instrument the real requests.Session; all HTTP traffic remains live.
        with mock.patch('supplier.requests.Session', TrackingSession):
            supplier.send_to_channel_from_subreddit(
                post, TEST_CHANNEL, os.getenv('R2T_TEST_SUBREDDIT', 'aww'), 'new', 25, self.config,
            )
        self.assertEqual(len(messages), 1, 'No Reddit submission reached Telegram')
        self.assert_delivery(messages[0])
        self.assertIn(self.run_id, messages[0].text)
        self.assertTrue(sessions)
        self.assertTrue(all(session.closed for session in sessions), 'Reddit sessions were left open')
        for sender in senders:
            self.assert_closed(sender)

    def test_cached_reddit_image_classification_and_delivery_needs_no_post_fetch(self):
        from utils.http_resources import session as http_session

        with http_session() as http:
            with mock.patch.object(http, 'send', wraps=http.send) as network:
                reddit = supplier.praw.Reddit(
                    user_agent=self.config['reddit']['user_agent'],
                    client_id=self.config['reddit']['client_id'],
                    client_secret=self.config['reddit']['client_secret'],
                    username=self.config['reddit']['username'],
                    password=self.config['reddit']['password'],
                    requestor_kwargs={'timeout': utils.REDDIT_TIMEOUT, 'session': http},
                )
                posts = reddit.subreddit(os.getenv('R2T_TEST_SUBREDDIT', 'aww')).new(limit=25)
                post = next((p for p in supplier.submissions_safe(posts) if p.url.startswith('https://i.redd.it/')
                             and p.url.lower().endswith(('.jpg', '.jpeg', '.png'))), None)
                self.assertIsNotNone(post, 'No native Reddit image in the test listing')
                before = network.call_count
                kind, url = utils.get_url(post)
                self.assertEqual(network.call_count, before, 'Classification fetched a full post/comment tree')
                self.assertEqual(kind, utils.TYPE_IMG)
                with self.sender() as sender:
                    result = sender.send_img(url, self.caption('cached Reddit image without comment fetch'))
                    self.assertEqual(result, utils.SupplyResult.SUCCESSFULLY)
                    self.assert_delivery(sender.messages[-1])
                    self.assertTrue(sender.messages[-1].photo)
                self.assert_closed(sender)


if __name__ == '__main__':
    unittest.main()
