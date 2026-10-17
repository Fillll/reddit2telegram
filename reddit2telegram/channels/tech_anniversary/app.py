"""Daily anniversary sweep; no Reddit listing is needed to send announcements."""

from utils import SupplyResult
from utils.anniversaries import AnniversaryAnnouncements, announcement_messages
from utils.tech import get_dev_channel


subreddit = 'all'
t_channel = get_dev_channel()
requires_submission = False


def send_post(submission, r2t):
    # supplier --test sets the initial destination. Never turn a test invocation
    # into production sends or update production anniversary delivery records.
    if r2t.t_channel == '@r_channels_test':
        for text in announcement_messages('@r_channels_test', 1, ['@reddit2telegram', '@r_channels']):
            r2t.send_text(text, parse_mode='HTML', disable_web_page_preview=True)
        return SupplyResult.STOP_THIS_SUPPLY

    result = AnniversaryAnnouncements(r2t).run()
    if result['status'] in ('failed', 'partial'):
        raise RuntimeError('Anniversary sweep needs attention; run {}'.format(result['_id']))
    return SupplyResult.STOP_THIS_SUPPLY
