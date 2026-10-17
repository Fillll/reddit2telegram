"""Promotion formatting without selecting or updating the daily promotion queue."""

from datetime import datetime

import utils


def what_channel(submodule_name_to_promte):
    submodule_to_promote = utils.channels_stuff.import_submodule(submodule_name_to_promte)
    return submodule_to_promote.t_channel


def get_tags(submodule_name_to_promte):
    tags_string = utils.channels_stuff.get_tags_for_submodule(submodule_name_to_promte)
    if not tags_string:
        return None
    return tags_string.split()


def make_nice_submission(submission, r2t, submodule_name_to_promte, extra_ending=None,
                         announcement_heading='', channel_to_promote=None, **kwargs):
    tags = get_tags(submodule_name_to_promte)
    tags_string = ''
    if tags is not None:
        if len(tags) > 0:
            tags_string = ' '.join(tags)
    if extra_ending is None:
        extra_ending = ''
    submission.title  # to make it non-lazy
    result = r2t.send_simple(submission,
        channel_to_promote=(channel_to_promote if channel_to_promote is not None
                            else what_channel(submodule_name_to_promte)),
        date=datetime.utcfromtimestamp(submission.created_utc).strftime('%Y %b %d'),
        tags=tags_string,
        extra_ending=extra_ending,
        announcement_heading=announcement_heading,
        text='{announcement_heading}{title}\n\n{self_text}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{date}\n{short_link}\nby {channel_to_promote}\n{tags}\n\n{extra_ending}',
        other='{announcement_heading}{title}\n{link}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{date}\n{short_link}\nby {channel_to_promote}\n{tags}\n\n{extra_ending}',
        album='{announcement_heading}{title}\n{link}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{date}\n{short_link}\nby {channel_to_promote}\n{tags}\n\n{extra_ending}',
        gif='{announcement_heading}{title}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{date}\n{short_link}\nby {channel_to_promote}\n{tags}\n\n{extra_ending}',
        img='{announcement_heading}{title}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{date}\n{short_link}\nby {channel_to_promote}\n{tags}\n\n{extra_ending}',
        video='{announcement_heading}{title}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{date}\n{short_link}\nby {channel_to_promote}\n{tags}\n\n{extra_ending}',
        gallery='{announcement_heading}{title}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{date}\n{short_link}\nby {channel_to_promote}\n{tags}\n\n{extra_ending}'
    )
    return result

