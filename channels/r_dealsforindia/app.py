from utils import weighted_random_subreddit

subreddit = weighted_random_subreddit({
    'dealsforindia': 1,
})

t_channel = '@r_dealsforindia'

def send_post(submission, r2t):
    return r2t.send_simple(submission,
        check_dups=True,
        min_upvotes_limit=1,
        text='{title}\n\n{self_text}\n\n/r/{subreddit_name}\n{short_link}\n{channel}',
        other='{title}\n{link}\n\n/r/{subreddit_name}\n{short_link}\n{channel}',
        album='{title}\n{link}\n\n/r/{subreddit_name}\n{short_link}\n{channel}',
        gif='{title}\n\n/r/{subreddit_name}\n{short_link}\n{channel}',
        img='{title}\n\n/r/{subreddit_name}\n{short_link}\n{channel}',
        video='{title}\n\n/r/{subreddit_name}\n{short_link}\n{channel}',
        gallery='{title}\n\n/r/{subreddit_name}\n{short_link}\n{channel}'
    )
