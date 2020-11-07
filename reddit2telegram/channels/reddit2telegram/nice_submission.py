def get_tags(submodule_name_to_promte):
    tags_filename = os.path.join('channels', submodule_name_to_promte, 'tags.txt')
    if not os.path.exists(tags_filename):
        return None
    with open(tags_filename, 'r') as tags_file:
        tags = tags_file.read()
        return tags.split()


def make_nice_submission(r2t, submission, submodule_name_to_promte):
    tags = get_tags(submodule_name_to_promte)
    if tags is not None:
        if len(tags) > 0:
            tags_string = ' '.join(tags)
    submission.title  # to make it non-lazy
    result = r2t.send_simple(submission,
        channel_to_promote=what_channel(submodule_name_to_promte),
        date=datetime.utcfromtimestamp(submission.created_utc).strftime('%Y %b %d'),
        tags=tags_string,
        text='{title}\n\n{self_text}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{date}\n{short_link}\nby {channel_to_promote}\n{tags}',
        other='{title}\n{link}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{date}\n{short_link}\nby {channel_to_promote}\n{tags}',
        album='{title}\n{link}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{date}\n{short_link}\nby {channel_to_promote}\n{tags}',
        gif='{title}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{date}\n{short_link}\nby {channel_to_promote}\n{tags}',
        img='{title}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{date}\n{short_link}\nby {channel_to_promote}\n{tags}',
        video='{title}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{date}\n{short_link}\nby {channel_to_promote}\n{tags}'
    )
    return result
