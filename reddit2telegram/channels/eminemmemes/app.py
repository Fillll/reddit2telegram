#encoding:utf-8

subreddit = 'EminemMemes+BadMeetsEvil+D12_+HailieJade'
t_channel = '@EminemMemes'


def send_post(submission, r2t):
    return r2t.send_simple(submission,
        text='{title}\n\n{self_text}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{short_link}',
        other='{title}\n{link}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{short_link}',
        album='{title}\n{link}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{short_link}',
        gif='{title}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{short_link}',
        img='{title}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{short_link}',
        video='{title}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{short_link}'
    )
