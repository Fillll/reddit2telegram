import subprocess
import os

from utils import SupplyResult, clean_after_module
from utils.tech import get_dev_channel
from task_queue import TaskStatus

import psutil


subreddit = "all"
t_channel = get_dev_channel()


def get_status_count_from_status_list(status_list, status_id):
    short_status_list = [status for status in status_list if status["_id"] == status_id]
    if len(short_status_list) == 0:
        return 0
    elif len(short_status_list) == 1:
        return short_status_list[0]["count"]
    else:
        raise ValueError


def send_post(submission, r2t):
    text_to_send = ""
    # Memory.
    free_memory_mb = psutil.virtual_memory().free / 1024**2
    text_to_send += f"Free memory: {free_memory_mb:.3f}MB.\n"
    # Disk.
    total_size = clean_after_module()
    text_to_send += "Deleted files: " + str(round(total_size / (1024.0**3), 3)) + "GB.\n"
    # Available disk.
    disk_report = os.statvfs("/")
    available_gigs = (disk_report.f_bavail * disk_report.f_frsize) / 1024**3
    text_to_send += f"Available disk space: {available_gigs:.3f}GB.\n"
    # Traffic.
    vnstat_output = subprocess.check_output(["vnstat", "-m"])
    current_month_traffic = str(vnstat_output).split("\\n")[-4].split(" | ")[-2].strip()
    text_to_send += f"Current month traffic: {current_month_traffic}.\n"
    current_month_estimate = str(vnstat_output).split("\\n")[-2].split("|")[-2].strip()
    text_to_send += f"Current month estimate: {current_month_estimate}.\n"
    # Task stati.
    status_list = r2t.tasks.aggregate([{"$group": {"_id": "$status", "count": {"$sum": 1}}}])
    text_to_send += "Tasks' stati:\n"
    status_list = list(status_list)
    tasks_stati = r2t.settings.find_one({"setting": "tasks-stati"})
    if tasks_stati is None:
        tasks_stati = dict()
    else:
        tasks_stati = tasks_stati["data"]
    deleted_cnt = 0
    max_cycles_cnt = 0
    for each_possible_status in TaskStatus:
        status_id = each_possible_status.value
        status_name = each_possible_status.name
        current_stat = tasks_stati.get(status_name, {"amt": 0, "cycles_cnt": 0})
        status_count = get_status_count_from_status_list(status_list, status_id)
        current_stat["amt"] += status_count
        current_stat["cycles_cnt"] += 1
        max_cycles_cnt = max(current_stat["cycles_cnt"], max_cycles_cnt)
        tasks_stati[status_name] = current_stat
        average_rate = current_stat["amt"] / max_cycles_cnt
        text_to_send += f"  →  {status_name} ({status_id}): {status_count} (avg: {average_rate:.3f})\n"
        deleted_cnt += r2t.tasks.delete_many({"status": status_id}).deleted_count
    text_to_send += f"Deleted tasks: {deleted_cnt}."
    r2t.settings.find_one_and_update(filter={"setting": "tasks-stati"}, update={"$set": {"data": tasks_stati}}, upsert=True)
    # ✅ Done.
    r2t.send_text(text_to_send)
    return SupplyResult.STOP_THIS_SUPPLY
