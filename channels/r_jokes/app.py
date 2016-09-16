#encoding:utf-8


subreddit = 'jokes'
t_channel = '@r_jokes'


def send_post(submission, bot):
    title = submission.title
    punchline = submission.selftext
    link = submission.short_link
    text = '%s\n\n%s\n\n%s' % (title, punchline, link)
    bot.sendMessage(t_channel, text)
    return True
