#encoding:utf-8

subreddit = 'Crypto_Currency_News+CryptoMarkets+CryptoCurrency'
t_channel = '@r_cryptocurrancy'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
