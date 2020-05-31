import os

from utils import TEMP_FOLDER
from utils import SupplyResult


subreddit = 'all'
t_channel = '@r_channels'


def send_post(submission, r2t):
    for filename in os.listdir(TEMP_FOLDER):
        if filename == 'empty.md':
            continue
        file_path = os.path.join(TEMP_FOLDER, filename)
        os.remove(file_path)
    return SupplyResult.STOP_THIS_SUPPLY
