"""Listing metadata must not fetch full comment trees or retain large pages."""

from pathlib import Path
import sys
from unittest import mock

import praw
import requests
from praw.models import Listing, ListingGenerator, Submission
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'implementations/implementations/python/reddit2telegram'))
import supplier
import utils


@pytest.fixture
def reddit():
    with requests.Session() as http:
        yield praw.Reddit(client_id='offline', client_secret='offline',
                          user_agent='r2t-offline-tests', check_for_async=False,
                          check_for_updates=False, requestor_kwargs={'session': http})


@pytest.mark.parametrize('extra,expected_type,expected_url', [
    ({}, utils.TYPE_IMG, 'https://i.redd.it/image.jpg'),
    ({'is_self': True}, utils.TYPE_TEXT, None),
    ({'is_video': True, 'media': {'reddit_video': {'fallback_url': 'https://v.redd.it/video.mp4'}}},
     utils.TYPE_VIDEO, 'https://v.redd.it/video.mp4'),
    ({'crosspost_parent_list': [{'is_video': True, 'media': {'reddit_video': {
        'fallback_url': 'https://v.redd.it/crosspost.mp4', 'is_gif': True}}}]},
     utils.TYPE_GIF, 'https://v.redd.it/crosspost.mp4'),
])
def test_cached_listing_post_never_fetches_comment_tree(reddit, extra, expected_type, expected_url):
    data = {'id': 'abc123', 'url': 'https://i.redd.it/image.jpg', 'is_self': False,
            'is_video': False, 'media': None, **extra}
    post = Submission(reddit, _data=data)
    assert not post._fetched
    with mock.patch.object(Submission, '_fetch', side_effect=AssertionError('Fetched full comment tree')):
        assert utils.get_url(post) == (expected_type, expected_url)


def test_cached_gallery_uses_listing_metadata(reddit):
    post = Submission(reddit, _data={
        'id': 'abc123', 'url': 'https://reddit.com/gallery/abc123', 'is_gallery': True,
        'gallery_data': {'items': [{'id': 1, 'media_id': 'image'}]},
        'media_metadata': {'image': {'s': {'u': 'https://preview.redd.it/image.jpg?auto=webp'}}},
    })
    with mock.patch.object(Submission, '_fetch', side_effect=AssertionError('Fetched full comment tree')):
        kind, gallery = utils.get_url(post)
    assert kind == utils.TYPE_GALLERY
    assert gallery[0][0]['url'] == 'https://i.redd.it/image.jpg'


def test_full_image_sender_uses_only_cached_listing_fields(reddit):
    post = Submission(reddit, _data={
        'id': 'abc123', 'url': 'https://i.redd.it/image.jpg', 'is_self': False,
        'is_video': False, 'media': None, 'title': 'Image fixture', 'selftext': '',
        'subreddit': 'aww', 'score': 100, 'over_18': False,
    })
    sender = object.__new__(utils.Reddit2TelegramSender)
    sender.t_channel = '@test'
    sender.send_img = mock.Mock(return_value=utils.SupplyResult.SUCCESSFULLY)
    with mock.patch.object(Submission, '_fetch', side_effect=AssertionError('Fetched full comment tree')):
        assert sender.send_simple(post) == utils.SupplyResult.SUCCESSFULLY
    assert sender.send_img.call_args.args[0] == 'https://i.redd.it/image.jpg'


@pytest.mark.parametrize('category', [
    'content_takedown', 'copyright_takedown', 'moderator', 'deleted', 'future_category',
])
@pytest.mark.parametrize('kind', ['text', 'img', 'video', 'gif', 'gallery', 'album', 'other'])
def test_removed_listing_rejected_before_score_media_or_send(reddit, category, kind):
    post = Submission(reddit, _data={'id': 'removed', 'removed_by_category': category})
    sender = object.__new__(utils.Reddit2TelegramSender)
    # No other attributes or sender resources exist: accessing them would fail.
    with mock.patch.object(Submission, '_fetch', side_effect=AssertionError('Fetched removed post')), \
            mock.patch.object(utils, 'get_url', side_effect=AssertionError('Classified removed post')):
        result = sender.send_simple(post, min_upvotes_limit=100, **{kind: True})
    assert result == utils.SupplyResult.DO_NOT_WANT_THIS_SUBMISSION


@pytest.mark.parametrize('metadata', [{}, {'removed_by_category': None}, {'removed_by_category': ''}])
@pytest.mark.parametrize('is_self', [False, True])
def test_unremoved_posts_still_send_without_fetching_optional_removal_field(reddit, metadata, is_self):
    post = Submission(reddit, _data={
        'id': 'normal', 'url': 'https://i.redd.it/image.jpg', 'is_self': is_self,
        'is_video': False, 'media': None, 'title': 'Normal post', 'selftext': 'Body',
        'subreddit': 'aww', 'score': 100, 'over_18': False, **metadata,
    })
    sender = object.__new__(utils.Reddit2TelegramSender)
    sender.t_channel = '@test'
    sender.send_img = mock.Mock(return_value=utils.SupplyResult.SUCCESSFULLY)
    sender.send_text = mock.Mock(return_value=utils.SupplyResult.SUCCESSFULLY)
    with mock.patch.object(Submission, '_fetch', side_effect=AssertionError('Fetched optional field')):
        assert sender.send_simple(post) == utils.SupplyResult.SUCCESSFULLY
    (sender.send_text if is_self else sender.send_img).assert_called_once()
    (sender.send_img if is_self else sender.send_text).assert_not_called()


@pytest.mark.parametrize('missing', ['score', 'url', 'title', 'over_18'])
def test_removal_discovered_during_hydration_never_sends_or_marks_duplicate(reddit, missing):
    data = {
        'id': 'removed', 'url': 'https://i.redd.it/image.jpg', 'is_self': False,
        'is_video': False, 'media': None, 'title': 'Removed by Reddit', 'selftext': '[removed]',
        'subreddit': 'aww', 'score': 100, 'over_18': False,
    }
    initial = dict(data)
    del initial[missing]
    post = Submission(reddit, _data=initial)
    sender = object.__new__(utils.Reddit2TelegramSender)
    sender.t_channel = '@test'
    sender.send_img = mock.Mock(side_effect=AssertionError('Sent removed post'))
    sender.dup_check_and_mark = mock.Mock(side_effect=AssertionError('Marked removed post'))

    def hydrate(self):
        self.__dict__.update(data, removed_by_category='content_takedown', _fetched=True)

    with mock.patch.object(Submission, '_fetch', autospec=True, side_effect=hydrate) as fetch:
        options = {'min_upvotes_limit': 200} if missing == 'score' else {}
        assert sender.send_simple(post, check_dups=True, **options) == utils.SupplyResult.DO_NOT_WANT_THIS_SUBMISSION
    fetch.assert_called_once()
    sender.send_img.assert_not_called()
    sender.dup_check_and_mark.assert_not_called()


def test_lazy_post_hydrates_once_before_optional_field_checks(reddit):
    post = Submission(reddit, id='abc123')

    def hydrate(self):
        self.__dict__.update(url='https://i.redd.it/image.jpg', is_self=False,
                             is_video=False, media=None, _fetched=True)

    with mock.patch.object(Submission, '_fetch', autospec=True, side_effect=hydrate) as fetch:
        assert utils.get_url(post) == (utils.TYPE_IMG, 'https://i.redd.it/image.jpg')
    fetch.assert_called_once()


@pytest.mark.parametrize('limit', [0, 1, 10, 25, 26, 100, None])
def test_smaller_pages_preserve_candidate_limit_order_and_pagination(reddit, limit):
    calls = []
    available = 113

    def page(url, params):
        calls.append(dict(params))
        start = int(params.get('after', 0))
        end = min(start + params['limit'], available)
        children = [{'kind': 't3', 'data': {'id': str(i)}} for i in range(start, end)]
        return Listing(reddit, _data={'children': children,
                                      'after': str(end) if end < available else None})

    iterator = ListingGenerator(reddit, '/r/offline/new', limit=limit)
    supplier._bound_listing_page_size(iterator)
    with mock.patch.object(reddit, 'get', side_effect=page):
        result = list(iterator)
    assert [post.id for post in result] == [str(i) for i in range(available if limit is None else min(limit, available))]
    assert all(call['limit'] <= 25 for call in calls)
    assert iterator.limit == limit
    if limit and limit <= 25:
        assert len(calls) == 1
    if limit == 100:
        assert len(calls) == 4
