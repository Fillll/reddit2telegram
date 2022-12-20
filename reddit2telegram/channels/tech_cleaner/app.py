import subprocess

from utils import SupplyResult, clean_after_module
from utils.tech import get_dev_channel
from task_queue import TaskStatus

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
    text_to_send += 'Deleted files: ' + str(round(total_size / (1024.0 ** 3), 3)) + 'GB.\n'
    # Traffic.
    vnstat_output = subprocess.check_output(['vnstat', '-m'])
    current_month_traffic = str(vnstat_output).split('\\n')[-4].split(' | ')[-2].strip()
    text_to_send += f'Current month traffic: {current_month_traffic}.\n'
    current_month_estimate = str(vnstat_output).split('\\n')[-2].split('|')[-2].strip()
    text_to_send += f'Current month estimate: {current_month_estimate}.\n'
    # Task statuses.
    status_list = r2t.tasks.aggregate([
        {
            '$group': {
                '_id': '$status',
                'count': {
                    '$sum': 1
                }
            }
        }
    ])
    text_to_send += 'Stati:\n'
    for status in list(status_list):
        status_id = status['_id']
        status_name = TaskStatus(status_id).name
        status_count = status['count']
        text_to_send += f'  →  {status_name} ({status_id}): {status_count}\n'
    deleted_cnt = r2t.tasks.delete_many({'status': TaskStatus.SUCCESS.value})
    text_to_send += f'Deleted tasks: {deleted_cnt.deleted_count}.'
    # ✅ Done.
    r2t.send_text(text_to_send)
    return SupplyResult.STOP_THIS_SUPPLY
