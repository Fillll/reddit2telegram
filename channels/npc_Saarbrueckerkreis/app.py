#encoding:utf-8

subreddit = 'Saarbrueckerkreis'
t_channel = '@Saarbrueckerkreis'

def send_comment(comment, r2t):

    title = comment.submission.title
    punchline = comment.body
    link = comment.permalink()
    text = '{title}\n\n{body}\n\nhttp://www.reddit.com{link}\n{channel}'.format(
            title=title, body=punchline, link=link, channel=t_channel)
    return r2t.send_text(text, disable_web_page_preview=True)
	
def send_post(submission, r2t):
    return r2t.send_simple(submission)
