#encoding:utf-8

t_channel = '@reddit_all'
subreddit = 'all'


def send_post(submission, r2t):
    return r2t.send_simple(submission,
        min_upvotes_limit=12345,
        text='{title}\n\n{self_text}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{short_link}',
        other='{title}\n{link}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{short_link}',
        album='{title}\n{link}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{short_link}',
        gif='{title}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{short_link}',
        img='{title}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{short_link}',
        video='{title}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{short_link}'
    )
