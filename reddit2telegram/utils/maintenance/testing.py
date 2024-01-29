from utils import *
from utils.tech import *
import yaml


with open('configs/prod.yml') as f:
    config = yaml.safe_load(f.read())
r2t = Reddit2TelegramSender('@r_channels_test', config)

import praw
reddit = praw.Reddit(
        user_agent=config['reddit']['user_agent'],
        client_id=config['reddit']['client_id'],
        client_secret=config['reddit']['client_secret'],
        username=config['reddit']['username'],
        password=config['reddit']['password']
    )

%load_ext autoreload
%autoreload 2


s = reddit.submission('c88zz9')


r2t.send_simple(s)

ffmpeg -i tmp/r_channels_test..mp4 -i tmp/r_channels_test..mp4.aac -c:v copy -c:a aac -strict experimental tmp/r_channels_test..1.mp4 -hide_banner -loglevel panic -y