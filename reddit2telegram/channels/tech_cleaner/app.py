import os

from utils import TEMP_FOLDER
from utils import SupplyResult
from utils.tech import get_dev_channel, short_sleep


subreddit = 'all'
t_channel = get_dev_channel()


def send_post(submission, r2t):
    total_size = 0
    for filename in os.listdir(TEMP_FOLDER):
        if filename == 'empty.md':
            continue
        file_path = os.path.join(TEMP_FOLDER, filename)
        total_size += os.path.getsize(file_path)
        os.remove(file_path)
    r2t.send_text(total_size)
    return SupplyResult.STOP_THIS_SUPPLY
