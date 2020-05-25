#encoding:utf-8

subreddit = 'netflixbestof+bestofnetflix+movie_club+truefilm+shittymoviedetails+ijustwatched'
t_channel = '@r_movieclub'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
