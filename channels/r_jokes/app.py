#encoding:utf-8


# Write here subreddit name. Like this one for /r/jokes.
subreddit = 'jokes'
# This is for your public telegram channel.
t_channel = '@r_jokes'


def send_post(submission, bot):
    # To read more about dealing with reddit submission please
    # visit https://praw.readthedocs.io/.
    title = submission.title
    punchline = submission.selftext
    link = submission.short_link
    text = '{}\n\n{}\n\n{}'.format(title, punchline, link)

    # To read more about sending massages to telegram please
    # visit https://github.com/nickoala/telepot/tree/master/examples/simple
    # with simple examples, or visit doc page: http://telepot.readthedocs.io/.
    bot.sendMessage(t_channel, text)

    # Return True, if this submission is suitable for sending and was sent,
    # if not – return False.
    return True
