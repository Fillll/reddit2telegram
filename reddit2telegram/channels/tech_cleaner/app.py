from utils import SupplyResult, clean_after_module
from utils.tech import get_dev_channel


subreddit = 'all'
t_channel = get_dev_channel()


def send_post(submission, r2t):
    total_size = clean_after_module()
    r2t.send_text('Deleted: ' + str(round(total_size / (1024.0 ** 3), 3)) + 'GB.')
    return SupplyResult.STOP_THIS_SUPPLY
