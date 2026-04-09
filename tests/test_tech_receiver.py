from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = REPO_ROOT / 'reddit2telegram'
sys.path.insert(0, str(APP_DIR))

from channels.tech_receiver import app as tech_receiver


class FakeSettings:
    def __init__(self):
        self.docs = {}

    def create_index(self, *args, **kwargs):
        return None

    def find_one(self, selector):
        doc = self.docs.get(selector['setting'])
        if doc is None:
            return None
        return dict(doc)

    def insert_one(self, doc):
        self.docs[doc['setting']] = dict(doc)

    def update_one(self, selector, update, upsert=False):
        key = selector['setting']
        doc = self.docs.get(key)
        if doc is None:
            if not upsert:
                return
            doc = {'setting': key}
            self.docs[key] = doc
        doc.update(update.get('$set', {}))

    def delete_one(self, selector):
        self.docs.pop(selector['setting'], None)

    def find_one_and_update(self, selector, update):
        self.update_one(selector, update, upsert=False)


def test_process_message_step_by_step_flow_saves_channel(monkeypatch):
    settings = FakeSettings()
    replies = []
    upserts = []

    monkeypatch.setattr(
        tech_receiver.utils.channels_stuff,
        'get_channel_doc',
        lambda channel: None
    )
    monkeypatch.setattr(
        tech_receiver.utils.channels_stuff,
        'upsert_channel',
        lambda channel, **kwargs: upserts.append((channel, kwargs))
    )

    send_reply = lambda user_id, text: replies.append((user_id, text))

    tech_receiver.process_message(
        'https://www.reddit.com/r/space/',
        1882084,
        settings,
        {'telegram': {'papa': '1882084'}},
        send_reply=send_reply,
    )
    tech_receiver.process_message(
        'https://t.me/r_space',
        1882084,
        settings,
        {'telegram': {'papa': '1882084'}},
        send_reply=send_reply,
    )
    tech_receiver.process_message(
        '#space #astronomy #nasa',
        1882084,
        settings,
        {'telegram': {'papa': '1882084'}},
        send_reply=send_reply,
    )

    assert upserts == [
        (
            'r_space',
            {
                'subreddit': 'space',
                'tags': '#space #astronomy #nasa',
            }
        )
    ]
    assert settings.find_one({'setting': tech_receiver._state_setting_name(1882084)}) is None
    assert replies[0][1] == 'Saved subreddit: r/space\nNow send channel (@name or t.me link).'
    assert replies[1][1] == 'Saved channel: @r_space\nNow send tags like #tag1 #tag2 #tag3'
    assert replies[2][1] == (
        'Saved channel:\n'
        'subreddit: r/space\n'
        'channel: @r_space\n'
        'tags: #space #astronomy #nasa'
    )


def test_process_message_single_message_updates_existing_channel(monkeypatch):
    settings = FakeSettings()
    replies = []
    upserts = []

    monkeypatch.setattr(
        tech_receiver.utils.channels_stuff,
        'get_channel_doc',
        lambda channel: {'submodule': channel.lower()}
    )
    monkeypatch.setattr(
        tech_receiver.utils.channels_stuff,
        'upsert_channel',
        lambda channel, **kwargs: upserts.append((channel, kwargs))
    )

    tech_receiver.process_message(
        'subreddit: https://www.reddit.com/r/space/\n'
        'channel: @r_space\n'
        'tags: #space #astronomy #nasa',
        1882084,
        settings,
        {'telegram': {'papa': '1882084'}},
        send_reply=lambda user_id, text: replies.append(text),
    )

    assert upserts == [
        (
            'r_space',
            {
                'subreddit': 'space',
                'tags': '#space #astronomy #nasa',
            }
        )
    ]
    assert replies == [
        'Updated channel:\n'
        'subreddit: r/space\n'
        'channel: @r_space\n'
        'tags: #space #astronomy #nasa'
    ]


def test_send_post_preserves_last_update_when_there_are_no_updates(monkeypatch):
    settings = FakeSettings()
    settings.insert_one({'setting': tech_receiver.LAST_UPDATE_SETTING, 'last_update': 42})

    monkeypatch.setattr(
        tech_receiver,
        '_load_config',
        lambda: {
            'db': {'host': 'localhost', 'name': 'reddit2telegram'},
            'telegram': {'papa': '1882084'}
        }
    )
    monkeypatch.setattr(tech_receiver, '_get_settings_collection', lambda config: settings)

    class FakeR2T:
        def get_updates(self, **kwargs):
            assert kwargs['offset'] == 43
            return []

        def forward_message(self, **kwargs):
            raise AssertionError('No messages should be forwarded when there are no updates.')

    result = tech_receiver.send_post(None, FakeR2T())

    assert result == tech_receiver.SupplyResult.STOP_THIS_SUPPLY
    assert settings.find_one({'setting': tech_receiver.LAST_UPDATE_SETTING})['last_update'] == 42
