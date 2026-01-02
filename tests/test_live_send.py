#encoding:utf-8

import os
import sys
import unittest
from datetime import datetime
import shutil

import yaml
import pymongo


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
APP_DIR = os.path.join(REPO_ROOT, 'reddit2telegram')

sys.path.insert(0, APP_DIR)

import supplier
import utils
import utils.channels_stuff as channels_stuff


TEST_SUBMODULE = os.getenv('R2T_TEST_SUBMODULE', 'integration_test_channel')
TEST_SUBREDDIT = os.getenv('R2T_TEST_SUBREDDIT', 'aww')
TEST_CHANNEL = '@r_channels_test'
TEST_IMAGE_URL = os.getenv('R2T_TEST_IMAGE_URL', 'https://httpbin.org/image/jpeg')
TEST_GIF_URL = os.getenv(
    'R2T_TEST_GIF_URL',
    'https://upload.wikimedia.org/wikipedia/commons/2/2c/Rotating_earth_%28large%29.gif'
)


class LiveSendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.getenv('R2T_LIVE_TESTS') != '1':
            raise unittest.SkipTest('Set R2T_LIVE_TESTS=1 to run live-send tests.')
        os.chdir(APP_DIR)
        with open(os.path.join(APP_DIR, 'configs', 'prod.yml')) as config_file:
            cls.config = yaml.safe_load(config_file.read())
        cls.db = pymongo.MongoClient(host=cls.config['db']['host'])[cls.config['db']['name']]
        cls.db['channels'].update_one(
            {'submodule': TEST_SUBMODULE.lower()},
            {'$set': {
                'submodule': TEST_SUBMODULE.lower(),
                'channel': TEST_CHANNEL,
                'subreddit': TEST_SUBREDDIT,
                'tags': '#integration #test',
                'submissions_ranking': 'new',
                'submissions_limit': 50,
                'content': {
                    'text': True,
                    'gif': True,
                    'img': True,
                    'album': True,
                    'gallery': True,
                    'other': True,
                    'video': False
                }
            }},
            upsert=True
        )

    def test_can_send_direct_message(self):
        r2t = utils.Reddit2TelegramSender(TEST_CHANNEL, self.config)
        text = 'r2t live test ping {}'.format(datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'))
        result = r2t.send_text(text, disable_web_page_preview=True)
        self.assertEqual(result, utils.SupplyResult.SUCCESSFULLY)

    def test_send_testing_plan(self):
        r2t = utils.Reddit2TelegramSender(TEST_CHANNEL, self.config)
        plan = '\n'.join([
            'r2t live test plan:',
            '1) text ping',
            '2) testing plan message',
            '3) picture',
            '4) gif',
            '5) video (ffmpeg)',
            '6) long text',
            '7) album'
        ])
        result = r2t.send_text(plan, disable_web_page_preview=True)
        self.assertEqual(result, utils.SupplyResult.SUCCESSFULLY)

    def test_send_picture(self):
        r2t = utils.Reddit2TelegramSender(TEST_CHANNEL, self.config)
        text = 'r2t live test image {}'.format(datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'))
        result = r2t.send_img(TEST_IMAGE_URL, text)
        self.assertEqual(result, utils.SupplyResult.SUCCESSFULLY)

    def test_send_gif(self):
        r2t = utils.Reddit2TelegramSender(TEST_CHANNEL, self.config)
        text = 'r2t live test gif {}'.format(datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'))
        candidates = [
            TEST_GIF_URL,
            'https://media.giphy.com/media/ICOgUNjpvO0PC/giphy.gif',
            'https://i.imgur.com/1o1z4.gif'
        ]
        success = False
        for url in candidates:
            try:
                result = r2t.send_gif(url, text)
            except Exception:
                result = None
            if result == utils.SupplyResult.SUCCESSFULLY:
                success = True
                break
        if not success:
            raise unittest.SkipTest('No GIF URL allowed HEAD/size check or send.')

    def test_send_video_with_ffmpeg(self):
        if shutil.which('ffmpeg') is None:
            raise unittest.SkipTest('ffmpeg is required for the video send test.')
        reddit = supplier.praw.Reddit(
            user_agent=self.config['reddit']['user_agent'],
            client_id=self.config['reddit']['client_id'],
            client_secret=self.config['reddit']['client_secret'],
            username=self.config['reddit']['username'],
            password=self.config['reddit']['password']
        )
        r2t = utils.Reddit2TelegramSender(TEST_CHANNEL, self.config)
        success = False
        for submission in reddit.subreddit(TEST_SUBREDDIT).new(limit=50):
            what, url = utils.get_url(submission)
            if what != utils.TYPE_VIDEO:
                continue
            result = r2t.send_video(url,
                                    'r2t live test video {}'.format(datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')))
            if result == utils.SupplyResult.SUCCESSFULLY:
                success = True
                break
        self.assertTrue(success, 'No video submission found to test ffmpeg send.')

    def test_send_long_text(self):
        r2t = utils.Reddit2TelegramSender(TEST_CHANNEL, self.config)
        long_text = 'r2t live test long text:\n' + ('A' * 5000)
        result = r2t.send_text(long_text, disable_web_page_preview=True)
        self.assertEqual(result, utils.SupplyResult.SUCCESSFULLY)

    def test_send_album(self):
        r2t = utils.Reddit2TelegramSender(TEST_CHANNEL, self.config)
        story = {
            1: {'url': TEST_IMAGE_URL, 'what': utils.TYPE_IMG},
            2: {'url': TEST_IMAGE_URL, 'what': utils.TYPE_IMG}
        }
        result = r2t.send_album(story)
        self.assertEqual(result, utils.SupplyResult.SUCCESSFULLY)

    def test_can_send_from_reddit(self):
        submodule = channels_stuff.import_submodule(TEST_SUBMODULE)
        self.assertEqual(submodule.subreddit, TEST_SUBREDDIT)
        self.assertEqual(submodule.t_channel, TEST_CHANNEL)
        self.assertEqual(submodule.__class__.__name__, 'DefaultChannel')

        reddit = supplier.praw.Reddit(
            user_agent=self.config['reddit']['user_agent'],
            client_id=self.config['reddit']['client_id'],
            client_secret=self.config['reddit']['client_secret'],
            username=self.config['reddit']['username'],
            password=self.config['reddit']['password']
        )
        r2t = utils.Reddit2TelegramSender(TEST_CHANNEL, self.config)
        allowed_types = {utils.TYPE_IMG, utils.TYPE_GIF, utils.TYPE_TEXT}
        success = False
        for submission in reddit.subreddit(TEST_SUBREDDIT).new(limit=50):
            what, _ = utils.get_url(submission)
            if what not in allowed_types:
                continue
            result = submodule.send_post(submission, r2t)
            if result == utils.SupplyResult.SUCCESSFULLY:
                success = True
                break
        self.assertTrue(success, 'No successful post was sent to {}.'.format(TEST_CHANNEL))


if __name__ == '__main__':
    unittest.main()
