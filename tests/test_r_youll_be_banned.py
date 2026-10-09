from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = REPO_ROOT / 'reddit2telegram'
sys.path.insert(0, str(APP_DIR))

from channels.r_youll_be_banned import app


def test_channel_has_the_requested_sources_and_destination():
    assert app.SUBREDDITS == (
        'youll_be_banned',
        'no_or_youll_be_banned',
        'Youll_Myabe_Be_Banned',
        'yes_or_youllbe_banned',
        'YesOrNoYouWontGetABan',
        'YoBanMe',
    )
    assert app.subreddit == '+'.join(app.SUBREDDITS)
    assert app.t_channel == '@r_youll_be_banned'


def test_channel_uses_the_standard_post_sender():
    class Sender:
        def __init__(self):
            self.submission = None

        def send_simple(self, submission):
            self.submission = submission
            return 'sent'

    submission = object()
    sender = Sender()

    assert app.send_post(submission, sender) == 'sent'
    assert sender.submission is submission
