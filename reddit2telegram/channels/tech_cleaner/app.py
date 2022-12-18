import subprocess

from utils import SupplyResult, clean_after_module
from utils.tech import get_dev_channel

import psutil


subreddit = 'all'
t_channel = get_dev_channel()


def send_post(submission, r2t):
    text_to_send = ''
    # Memory.
    free_memory_mb = psutil.virtual_memory().free / 1024**2
    text_to_send += f'Free memory: {free_memory_mb:.3f}MB.\n'
    # Disk.
    total_size = clean_after_module()
    text_to_send += 'Deleted: ' + str(round(total_size / (1024.0 ** 3), 3)) + 'GB.\n'
    # Traffic.
    vnstat_output = subprocess.check_output(['vnstat', '-m'])
    current_month_traffic = str(vnstat_output).split('\\n')[-4].split(' | ')[-2].strip()
    text_to_send += f'Current month traffic: {current_month_traffic}.'
    r2t.send_text(text_to_send)
    return SupplyResult.STOP_THIS_SUPPLY
